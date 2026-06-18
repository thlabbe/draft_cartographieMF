""" review classification script

Utility to interactively validate and / or remove ambigousity on the pds classification.

"""

import enum
import json
import tkinter 
from cartographie.utils import load_config, connect_to_db
from cartographie.types import Member_Types

from tkinter import ttk

import duckdb
# import sv_ttk


class List_items(ttk.Frame):
    def __init__(self, parent, items):
        super().__init__(parent)
        self.items = items
        self.current_index = -1
        self.selected_widget = None

        self.selected_item = None
        self.canvas = tkinter.Canvas(self, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient=tkinter.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.default_bg = self.canvas.cget("background")
        self.default_fg = "black"
        self.selected_bg = "#0b5ed7"
        self.selected_fg = "white"

        self.scrollbar.pack(side=tkinter.RIGHT, fill=tkinter.Y)
        self.canvas.pack(side=tkinter.LEFT, fill=tkinter.BOTH, expand=True)

        self.list_frame = ttk.Frame(self.canvas)
        self.canvas_window_id = self.canvas.create_window((0, 0), window=self.list_frame, anchor=tkinter.NW)

        self.list_frame.bind("<Configure>", self._on_list_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<Enter>", self._bind_mousewheel)
        self.canvas.bind("<Leave>", self._unbind_mousewheel)

        for item in items:
            label = ttk.Label(self.list_frame, text=item)
            
            # label.bind("<Up>", lambda event: self.navigate(-1))
            # label.bind("<Down>", lambda event: self.navigate(1))
            label.pack(side=tkinter.TOP, fill=tkinter.X)

    def navigate(self, direction):
        self.current_index = (self.current_index + direction) % len(self.items)
        self.selected_item = self.items[self.current_index]
        #self.on_select_callback(selected_item)

    def _on_list_frame_configure(self, _event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self.canvas.itemconfigure(self.canvas_window_id, width=event.width)

    def _bind_mousewheel(self, _event):
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _unbind_mousewheel(self, _event):
        self.canvas.unbind_all("<MouseWheel>")

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def select_widget(self, widget):
        if self.selected_widget is not None and self.selected_widget.winfo_exists():
            self.selected_widget.configure(bg=self.default_bg, fg=self.default_fg)

        self.selected_widget = widget
        if self.selected_widget is not None and self.selected_widget.winfo_exists():
            self.selected_widget.configure(bg=self.selected_bg, fg=self.selected_fg)

    def clear_selection(self):
        if self.selected_widget is not None and self.selected_widget.winfo_exists():
            self.selected_widget.configure(bg=self.default_bg, fg=self.default_fg)
        self.selected_widget = None


def global_widget(root):
    """
    wiget principale:
    - présente la liste des PDS en indiquant leur Type. l'utilisateur peut modifier le type dun PDS.
    - quand l'utilisateur a selectionné un PDS, la liste des Membres du PDS est affichée avec leur Type. 
    - quand le l'utilisateur a selectionné un membre, le code source du membre est affiché avec la possibilité de selectionner le Type du membre.
    """    
    vbox = ttk.Frame(root)
    vbox.pack(side=tkinter.TOP, fill=tkinter.BOTH, expand=True)

    # PDS List with scrollbar
    pds_container = List_items(vbox, [])
    pds_container.pack(side=tkinter.LEFT, fill=tkinter.Y)

    # Member List with scrollbar
    member_container = List_items(vbox, [])
    member_container.pack(side=tkinter.LEFT, fill=tkinter.Y)

    choose_type_frame, choose_type_var = add_choose_type_frame(vbox)

    member_code_frame = ttk.Frame(vbox)
    member_code_frame.pack(side=tkinter.LEFT, fill=tkinter.BOTH, expand=True)

    status_var = tkinter.StringVar(value="PDS: -   |   MEMBRE: -")
    statusbar = ttk.Label(root, textvariable=status_var, relief=tkinter.SUNKEN, anchor=tkinter.W)
    statusbar.pack(side=tkinter.BOTTOM, fill=tkinter.X)

    setattr(vbox, "pds_container", pds_container)
    setattr(vbox, "member_container", member_container)
    setattr(vbox, "choose_type_frame", choose_type_frame)
    setattr(vbox, "choose_type_var", choose_type_var)
    setattr(vbox, "member_code_frame", member_code_frame)
    setattr(vbox, "status_var", status_var)
    setattr(vbox, "pds_widget_map", {})
    setattr(vbox, "member_widget_map", {})
    setattr(vbox, "current_pds_name", None)
    setattr(vbox, "current_member_name", None)
    setattr(vbox, "current_member_widget", None)

    return vbox

def add_choose_type_frame(vbox):
    """
    add a frame to choose the type of the selected PDS or Member.
    """
    choose_type_frame = ttk.Frame(vbox)
    choose_type_label = ttk.Label(choose_type_frame, text="Choose Type:")
    choose_type_label.pack(side=tkinter.TOP, anchor=tkinter.W, padx=5, pady=5)
    choose_type_var = tkinter.StringVar()
    for member_type in Member_Types:
        radio_button = ttk.Radiobutton(choose_type_frame, text=member_type.name, variable=choose_type_var, value=member_type.name)
        radio_button.pack(side=tkinter.TOP, anchor=tkinter.W, padx=5, pady=2)
    validate_button = ttk.Button(choose_type_frame, text="Valider")
    validate_button.pack(side=tkinter.TOP, anchor=tkinter.W, padx=5, pady=(10, 5))
    setattr(vbox, "validate_button", validate_button)
    return choose_type_frame, choose_type_var


def clear_children(frame):
    for child in frame.winfo_children():
        child.destroy()


def update_status(vbox, pds_name=None, member_name=None):
    current_pds = pds_name if pds_name else "-"
    current_member = member_name if member_name else "-"
    vbox.status_var.set(f"PDS: {current_pds}   |   MEMBRE: {current_member}")


def format_member_label(member_name, member_type, human_reviewed):
    reviewed_marker = "[x]" if human_reviewed else "[ ]"
    return f"{reviewed_marker} {member_name} ({member_type})"


def mark_member_reviewed(cnx, pds_name, member_name):
    cursor = cnx.cursor()
    cursor.execute(
        """
        UPDATE members
        SET human_reviewed = TRUE
        WHERE pds_id = (SELECT id FROM pds WHERE name = ?) AND name = ?
        """,
        (pds_name, member_name),
    )
    cnx.commit()


def validate_selected_member(cnx, vbox):
    pds_name = vbox.current_pds_name
    member_name = vbox.current_member_name
    if not pds_name or not member_name:
        return

    selected_type = vbox.choose_type_var.get() or Member_Types.UNDEFINED.name
    cursor = cnx.cursor()
    cursor.execute(
        """
        SELECT type, human_reviewed
        FROM members
        WHERE pds_id = (SELECT id FROM pds WHERE name = ?) AND name = ?
        """,
        (pds_name, member_name),
    )
    row = cursor.fetchone()
    if not row:
        return

    current_type, current_human_reviewed = row
    next_human_reviewed = True

    if current_type != selected_type or not current_human_reviewed:
        cursor.execute(
            """
            UPDATE members
            SET type = ?, human_reviewed = TRUE
            WHERE pds_id = (SELECT id FROM pds WHERE name = ?) AND name = ?
            """,
            (selected_type, pds_name, member_name),
        )
        cnx.commit()

    member_widget = vbox.current_member_widget
    if member_widget is not None and member_widget.winfo_exists():
        member_data = vbox.member_widget_map.get(member_widget)
        if member_data is not None:
            member_data["member_type"] = selected_type
            member_data["human_reviewed"] = next_human_reviewed
        member_widget.configure(
            text=format_member_label(member_name, selected_type, next_human_reviewed)
        )

def on_pds_selected(event, cnx, vbox):
    """
    callback when a PDS is selected in the list. fetch the list of members for the selected PDS.

    """
    # empty the member list and code frames
    member_list_frame = vbox.member_container.list_frame
    clear_children(member_list_frame)
    member_code_frame = vbox.member_code_frame
    clear_children(member_code_frame)
    vbox.member_container.clear_selection()
    if vbox.choose_type_frame.winfo_ismapped():
        vbox.choose_type_frame.pack_forget()

    pds_name = vbox.pds_widget_map.get(event.widget, event.widget.cget("text"))
    pds_list_frame = vbox.pds_container.list_frame
    pds_widgets = pds_list_frame.winfo_children()
    if event.widget in pds_widgets:
        vbox.pds_container.current_index = pds_widgets.index(event.widget)
    vbox.pds_container.select_widget(event.widget)
    vbox.current_pds_name = pds_name
    vbox.current_member_name = None
    vbox.current_member_widget = None
    update_status(vbox, pds_name=pds_name)
    fetch_member_list(cnx, vbox, pds_name)



def on_member_selected(event, cnx, vbox, pds_name):
    """
    callback when a member is selected in the list. fetch the code for the selected member.
    """
    member_data = vbox.member_widget_map.get(
        event.widget,
        {
            "member_name": event.widget.cget("text"),
            "member_type": Member_Types.UNDEFINED.name,
            "human_reviewed": False,
        },
    )
    member_name = member_data["member_name"]
    member_type = member_data["member_type"]
    human_reviewed = member_data["human_reviewed"]
    member_list_frame = vbox.member_container.list_frame
    member_widgets = member_list_frame.winfo_children()
    if event.widget in member_widgets:
        vbox.member_container.current_index = member_widgets.index(event.widget)
    vbox.member_container.select_widget(event.widget)
    vbox.current_pds_name = pds_name
    vbox.current_member_name = member_name
    vbox.current_member_widget = event.widget
    update_status(vbox, pds_name=pds_name, member_name=member_name)

    fetch_member_code(cnx, vbox, pds_name, member_name)

def on_member_key(event, cnx, vbox, pds_name):
    """
    callback for keyboard navigation in member list.
    """
    children = vbox.member_container.list_frame.winfo_children()
    if not children:
        return
    
    if event.keysym == "Down":
        vbox.member_container.current_index = min(vbox.member_container.current_index + 1, len(children) - 1)
    elif event.keysym == "Up":
        vbox.member_container.current_index = max(vbox.member_container.current_index - 1, 0)
    else:
        return
    
    widget = children[vbox.member_container.current_index]
    vbox.member_container.select_widget(widget)
    member_data = vbox.member_widget_map.get(
        widget,
        {
            "member_name": widget.cget("text"),
            "member_type": Member_Types.UNDEFINED.name,
            "human_reviewed": False,
        },
    )
    member_name = member_data["member_name"]
    member_type = member_data["member_type"]
    human_reviewed = member_data["human_reviewed"]
    vbox.current_pds_name = pds_name
    vbox.current_member_name = member_name
    vbox.current_member_widget = widget

    update_status(vbox, pds_name=pds_name, member_name=member_name)
    fetch_member_code(cnx, vbox, pds_name, member_name)

    

def fetch_pds_list(cnx, vbox):
    """
    fetch the list of PDS from the database and display them in the pds_list_frame.
    """
    pds_list_frame = vbox.pds_container.list_frame
    clear_children(pds_list_frame)
    vbox.pds_widget_map = {}
    vbox.pds_container.clear_selection()
    vbox.member_container.clear_selection()
    vbox.member_widget_map = {}
    update_status(vbox)

    cursor = cnx.cursor()
    cursor.execute("""
        SELECT p.name,
               COALESCE(COUNT(*), 0) as total_members,
               COALESCE(SUM(CASE WHEN m.human_reviewed = TRUE THEN 1 ELSE 0 END), 0) as reviewed_members
        FROM pds p
        LEFT JOIN members m ON p.id = m.pds_id
        GROUP BY p.id, p.name
        ORDER BY p.name
    """)
    pds_list = cursor.fetchall()
    
    if len(pds_list) > 0:
        vbox.pds_container.current_index = 0
        vbox.pds_container.selected_item = pds_list[0]

    for row in pds_list:
        pds_name = row[0]
        total_members = row[1]
        reviewed_members = row[2]
        label = tkinter.Label(
            pds_list_frame,
            text=f"{pds_name} ({reviewed_members}/{total_members})",
            anchor=tkinter.W,
            bg=vbox.pds_container.default_bg,
            fg=vbox.pds_container.default_fg,
            padx=4,
        )
        vbox.pds_widget_map[label] = pds_name
        label.bind("<Button-1>", lambda event, cnx=cnx, vbox=vbox: on_pds_selected(event, cnx, vbox))
        label.bind("<Up>", lambda event, cnx=cnx, vbox=vbox: vbox.pds_container.navigate(-1))
        label.bind("<Down>", lambda event, cnx=cnx, vbox=vbox: vbox.pds_container.navigate(1))
        label.pack(side=tkinter.TOP, fill=tkinter.X)

def fetch_member_list(cnx, vbox, pds_name):
    """
    fetch the list of members from the database and display them in the member_list_frame.
    """
    member_list_frame = vbox.member_container.list_frame
    clear_children(member_list_frame)
    vbox.member_widget_map = {}
    vbox.member_container.clear_selection()
    clear_children(vbox.member_code_frame)
    if vbox.choose_type_frame.winfo_ismapped():
        vbox.choose_type_frame.pack_forget()

    cursor = cnx.cursor()
    cursor.execute(
        """
        SELECT name, type, human_reviewed
        FROM members
        WHERE pds_id = (SELECT id FROM pds WHERE name = ?)
        ORDER BY human_reviewed ASC, name ASC
        """,
        (pds_name,),
    )
    member_list = cursor.fetchall()

    for member_name, member_type, human_reviewed in member_list:
        label = tkinter.Label(
            member_list_frame,
            text=format_member_label(member_name, member_type, human_reviewed),
            anchor=tkinter.W,
            bg=vbox.member_container.default_bg,
            fg=vbox.member_container.default_fg,
            padx=4,
        )
        vbox.member_widget_map[label] = {
            "member_name": member_name,
            "member_type": member_type,
            "human_reviewed": human_reviewed,
        }
        label.bind("<Button-1>", lambda event, cnx=cnx, vbox=vbox, pds_name=pds_name: on_member_selected(event, cnx, vbox, pds_name))
        label.bind("<Up>", lambda event, cnx=cnx, vbox=vbox, pds_name=pds_name: on_member_key(event, cnx, vbox, pds_name))
        label.bind("<Down>", lambda event, cnx=cnx, vbox=vbox, pds_name=pds_name: on_member_key(event, cnx, vbox, pds_name))
        label.pack(side=tkinter.TOP, fill=tkinter.X)

def fetch_member_code(cnx, vbox, pds_name, member_name):
    """
    fetch the code of a member from the database and display it in the member_code_frame.
    """
    member_code_frame = vbox.member_code_frame
    clear_children(member_code_frame)

    if not vbox.choose_type_frame.winfo_ismapped():
        vbox.choose_type_frame.pack(
            side=tkinter.LEFT,
            fill=tkinter.Y,
            expand=False,
            padx=(8, 0),
            before=vbox.member_code_frame,
        )

    cursor = cnx.cursor()
    cursor.execute(
        "SELECT type FROM members WHERE pds_id = (SELECT id FROM pds WHERE name = ?) AND name = ?",
        (pds_name, member_name),
    )
    member_type_row = cursor.fetchone()
    if member_type_row:
        vbox.choose_type_var.set(member_type_row[0])
    vbox.current_pds_name = pds_name
    vbox.current_member_name = member_name

    cursor.execute("SELECT line_no, content FROM member_content WHERE member_id = (SELECT id FROM members WHERE pds_id = (SELECT id FROM pds WHERE name = ?) AND name = ?) ORDER BY line_no", (pds_name, member_name))
    code_lines = cursor.fetchall()

    text_widget = tkinter.Text(member_code_frame)
    for line_no, content in code_lines:
        text_widget.insert(tkinter.END, f"{line_no}: {content}\n")
    text_widget.pack(side=tkinter.TOP, fill=tkinter.BOTH, expand=True)

    vbox.validate_button.configure(command=lambda cnx=cnx, vbox=vbox: validate_selected_member(cnx, vbox))


if __name__ == "__main__":

    root = tkinter.Tk()
    root.title("Review Classification")
    root.geometry("800x600")

    # Apply the dark theme
    # sv_ttk.set_theme("dark")

    vbox = global_widget(root)

    # charger le projet.json et se connecter à la base de données
    
    ctx = load_config("cardif.project.json")
    cnx = connect_to_db(ctx)

    fetch_pds_list(cnx, vbox)


    # Start the Tkinter event loop
    root.mainloop()