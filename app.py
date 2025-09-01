#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Follow-up System - Sistema local de cadastro e follow-up de contatos
Versão: v6.7 (UI refinada, curso como dropdown padronizado também nos filtros, Observações expansiva)
Novidades:
- Curso/Interesse agora usa uma lista única padronizada em todo o app (formulário e filtros):
  ["Inglês", "Espanhol", "Informática", "Profissionalizante", "Robótica"].
- Área de Observações maior por padrão e expansiva (ocupa toda a largura e cresce com a janela).
- Mantidos: datas DD/MM/AAAA com digitação livre (8 dígitos), autoformatação de telefone e mensalidade.
- Campo "Data de follow-up" segue removido (form, tabela e CSV).
"""

import sqlite3
import csv
import os
import datetime
import re
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

DB_FILE = "contacts.db"

COLUMNS = [
    ("id", "ID"),
    ("name", "Nome"),
    ("phone", "Telefone"),
    ("email", "Email"),
    ("course", "Curso/Interesse"),
    ("visit_date", "Data da visita"),
    ("status", "Status"),
    ("monthly_fee", "Valor mensalidade"),
    ("how_found", "Como conheceu"),
    ("course_for", "Para quem é"),
    ("attended_by", "Atendido por"),
    ("notes", "Observações"),
]

DATE_FMT = "%d/%m/%Y"  # DD/MM/AAAA

# Lista padronizada de cursos para formulário e filtros
COURSES = ["Inglês", "Espanhol", "Informática", "Profissionalizante", "Robótica"]

# Altura padrão da caixa de Observações
NOTES_DEFAULT_HEIGHT = 8

# --------------------- Helpers de formatação ---------------------
def _only_digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")

def format_ddmmyyyy_from_digits(s: str) -> str | None:
    digits = _only_digits(s)
    if len(digits) != 8:
        return None
    d, m, y = digits[0:2], digits[2:4], digits[4:8]
    try:
        _ = datetime.datetime(int(y), int(m), int(d))
        return f"{d}/{m}/{y}"
    except Exception:
        return None

def format_br_phone_from_digits(s: str) -> str | None:
    d = re.sub(r"\D", "", s or "")
    # limita a no máximo 11 dígitos (evita “sobra” se colar texto grande)
    d = d[:11]

    if len(d) == 11:  # Celular com DDD
        return f"({d[0:2]}) {d[2:7]}-{d[7:]}"
    if len(d) == 10:  # Fixo com DDD (usado só no FocusOut)
        return f"({d[0:2]}) {d[2:6]}-{d[6:]}"
    if len(d) == 9:   # Celular sem DDD
        return f"{d[0:5]}-{d[5:]}"
    if len(d) == 8:   # Fixo sem DDD
        return f"{d[0:4]}-{d[4:]}"
    return None


def init_db():
    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()
    # tabela base
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT,
            email TEXT,
            course TEXT,
            visit_date TEXT,
            status TEXT,
            followup_date TEXT,
            notes TEXT
        )
        """
    )
    con.commit()

    # garantir novas colunas
    cur.execute("PRAGMA table_info(contacts)")
    cols = {row[1] for row in cur.fetchall()}

    def add_col(col_name, col_type="TEXT"):
        cur.execute(f"ALTER TABLE contacts ADD COLUMN {col_name} {col_type}")
        con.commit()

    for col in ["monthly_fee", "how_found", "course_for", "attended_by"]:
        if col not in cols:
            add_col(col)

    con.close()

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Follow-up System - Cadastro de Contatos")
        # self.geometry("1320x860")
        self.state("zoomed")
        self.minsize(1200, 760)

        style = ttk.Style(self)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        elif "clam" in style.theme_names():
            style.theme_use("clam")

        # Variáveis de filtros
        self.var_search = tk.StringVar()
        self.var_filter_phone = tk.StringVar()
        self.var_filter_att = tk.StringVar(value="Todos")
        self.var_filter_course = tk.StringVar(value="Todos")
        self.var_filter_status = tk.StringVar(value="Todos")
        self.var_filter_from = tk.StringVar()  # dd/mm/aaaa (8 dígitos ok)
        self.var_filter_to = tk.StringVar()    # dd/mm/aaaa (8 dígitos ok)

        # Variáveis do formulário
        self.var_name = tk.StringVar()
        self.var_phone = tk.StringVar()
        self.var_email = tk.StringVar()
        self.var_course = tk.StringVar()
        self.var_visit_date = tk.StringVar()
        self.var_status = tk.StringVar(value="Novo")
        self.var_monthly_fee = tk.StringVar()
        self.var_how_found = tk.StringVar(value="Indicação")
        self.var_course_for = tk.StringVar(value="Próprio")
        self.var_attended_by = tk.StringVar()
        self.var_notes = tk.StringVar()  # fallback se Text não existir

        self.create_menu()
        self.create_topbar()
        self.create_form()
        self.create_table()
        self.bind_events()

        self.refresh_filter_options()
        self.refresh_table()

    # --------------------- UI: menu e topbar ---------------------
    def create_menu(self):
        menubar = tk.Menu(self)
        filemenu = tk.Menu(menubar, tearoff=0)
        filemenu.add_command(label="Exportar CSV...", command=self.export_csv)
        filemenu.add_separator()
        filemenu.add_command(label="Sair", command=self.quit)
        menubar.add_cascade(label="Arquivo", menu=filemenu)

        helpmenu = tk.Menu(menubar, tearoff=0)
        helpmenu.add_command(label="Sobre", command=self.show_about)
        menubar.add_cascade(label="Ajuda", menu=helpmenu)

        self.config(menu=menubar)

    def create_topbar(self):
        top = ttk.Frame(self, padding=(10, 10, 10, 0))
        top.pack(fill=tk.X)

        # ---------- LINHA 0: BUSCAS ----------
        search_row = ttk.Frame(top)
        search_row.pack(fill=tk.X)

        ttk.Label(search_row, text="Buscar por nome:").grid(row=0, column=0, sticky=tk.W, padx=(0, 6))
        e_name = ttk.Entry(search_row, textvariable=self.var_search)
        e_name.grid(row=0, column=1, sticky="ew", padx=(0, 18))   # << cresce

        ttk.Label(search_row, text="Buscar por telefone:").grid(row=0, column=2, sticky=tk.W, padx=(0, 6))
        e_phone = ttk.Entry(search_row, textvariable=self.var_filter_phone)
        e_phone.grid(row=0, column=3, sticky="ew", padx=(0, 18))  # << cresce

        # Coluna "spacer" para empurrar a logo sem roubar espaço dos inputs
        ttk.Frame(search_row).grid(row=0, column=4, sticky="ew")

        # Logo no canto direito (coluna fixa)
        self.logo_img = None
        try:
            from PIL import Image, ImageTk
            img = Image.open("background-logo.png")
            img = img.resize((110, 48))  # ajuste aqui se quiser menor/maior
            self.logo_img = ImageTk.PhotoImage(img)
        except Exception:
            # fallback simples caso PIL não esteja instalado
            try:
                self.logo_img = tk.PhotoImage(file="background-logo.png")
            except Exception:
                self.logo_img = None

        if self.logo_img:
            ttk.Label(search_row, image=self.logo_img).grid(row=0, column=5, sticky="e", padx=(6, 0))

        # >>> Distribuição de espaço: 1 e 3 (inputs) recebem mais peso; 4 é o spacer; 5 é fixo
        search_row.grid_columnconfigure(1, weight=3, minsize=420)   # Nome (grande)
        search_row.grid_columnconfigure(3, weight=2, minsize=320)   # Telefone (bom tamanho)
        search_row.grid_columnconfigure(4, weight=1)                # Spacer elástico
        search_row.grid_columnconfigure(5, weight=0)                # Logo (fixo)

        # Autoformatação no filtro de telefone
        self.attach_phone_autofmt(e_phone, self.var_filter_phone)

        # ---------- LINHA 1: FILTROS ----------
        filt_row = ttk.Frame(top)
        filt_row.pack(fill=tk.X, pady=(6, 0))

        c = 0
        ttk.Label(filt_row, text="Atendido por:").grid(row=0, column=c, sticky=tk.W); c += 1
        self.cb_att = ttk.Combobox(filt_row, textvariable=self.var_filter_att, state="readonly", width=16, values=["Todos"])
        self.cb_att.grid(row=0, column=c, sticky=tk.W, padx=(4, 10)); c += 1

        ttk.Label(filt_row, text="Curso:").grid(row=0, column=c, sticky=tk.W); c += 1
        # AGORA padronizado: "Todos" + COURSES (não depende mais do banco)
        self.cb_course = ttk.Combobox(
            filt_row, textvariable=self.var_filter_course, state="readonly", width=16,
            values=["Todos"] + COURSES
        )
        self.cb_course.grid(row=0, column=c, sticky=tk.W, padx=(4, 10)); c += 1

        ttk.Label(filt_row, text="Status:").grid(row=0, column=c, sticky=tk.W); c += 1
        self.cb_status = ttk.Combobox(filt_row, textvariable=self.var_filter_status, state="readonly", width=16, values=["Todos"])
        self.cb_status.grid(row=0, column=c, sticky=tk.W, padx=(4, 10)); c += 1

        ttk.Label(filt_row, text="Visita de:").grid(row=0, column=c, sticky=tk.W); c += 1
        e_from = ttk.Entry(filt_row, textvariable=self.var_filter_from, width=15)
        e_from.grid(row=0, column=c, sticky=tk.W, padx=(4, 6)); c += 1
        ttk.Label(filt_row, text="até:").grid(row=0, column=c, sticky=tk.W, padx=(0, 4)); c += 1
        e_to = ttk.Entry(filt_row, textvariable=self.var_filter_to, width=15)
        e_to.grid(row=0, column=c, sticky=tk.W, padx=(0, 8)); c += 1

        ttk.Button(filt_row, text="Aplicar", command=self.refresh_table).grid(row=0, column=c, padx=(0, 6)); c += 1
        ttk.Button(filt_row, text="Limpar filtros", command=self.clear_filters).grid(row=0, column=c, padx=(0, 6)); c += 1
        ttk.Button(filt_row, text="Exportar CSV", command=self.export_csv).grid(row=0, column=c)

        # Autoformatação de datas nos filtros
        self.attach_date_autofmt(e_from, self.var_filter_from)
        self.attach_date_autofmt(e_to, self.var_filter_to)

    # --------------------- UI: formulário ---------------------
    def create_form(self):
        form = ttk.LabelFrame(self, text="Dados do contato", padding=10)
        form.pack(fill=tk.X, padx=10, pady=10)

        # ===== Linha única (labels em cima, inputs embaixo) =====
        row_top = ttk.Frame(form)
        row_top.pack(fill=tk.X, pady=4)

        c = 0
        ttk.Label(row_top, text="Nome *").grid(row=0, column=c, sticky=tk.W); c += 1
        ttk.Label(row_top, text="Telefone").grid(row=0, column=c, sticky=tk.W); c += 1
        ttk.Label(row_top, text="Email").grid(row=0, column=c, sticky=tk.W); c += 1
        ttk.Label(row_top, text="Curso/Interesse").grid(row=0, column=c, sticky=tk.W); c += 1
        ttk.Label(row_top, text="Data da visita").grid(row=0, column=c, sticky=tk.W); c += 1
        ttk.Label(row_top, text="Status").grid(row=0, column=c, sticky=tk.W); c += 1
        ttk.Label(row_top, text="Valor de mensalidade (R$)").grid(row=0, column=c, sticky=tk.W); c += 1

        c = 0
        # Nome (um pouquinho maior)
        e_name = ttk.Entry(row_top, textvariable=self.var_name, width=50)
        e_name.grid(row=1, column=c, padx=(0, 12), sticky=tk.W); c += 1

        # Telefone (autoformatação)
        e_phone_form = ttk.Entry(row_top, textvariable=self.var_phone, width=30)
        e_phone_form.grid(row=1, column=c, padx=(0, 12), sticky=tk.W); c += 1
        self.attach_phone_autofmt(e_phone_form, self.var_phone)

        # Email
        ttk.Entry(row_top, textvariable=self.var_email, width=35)\
            .grid(row=1, column=c, padx=(0, 12), sticky=tk.W); c += 1

        # Curso (dropdown padronizado)
        cb_course_form = ttk.Combobox(
            row_top, textvariable=self.var_course, state="readonly",
            values=COURSES, width=18
        )
        cb_course_form.grid(row=1, column=c, padx=(0, 12), sticky=tk.W); c += 1

        # Data da visita (autoformatação)
        e_visit = ttk.Entry(row_top, textvariable=self.var_visit_date, width=15)
        e_visit.grid(row=1, column=c, padx=(0, 12), sticky=tk.W); c += 1
        self.attach_date_autofmt(e_visit, self.var_visit_date)

        # Status
        status_cb = ttk.Combobox(
            row_top, textvariable=self.var_status,
            values=["Novo", "Em contato", "Retornar ligação", "Fechou matrícula", "Sem interesse"],
            width=18, state="readonly"
        )
        status_cb.grid(row=1, column=c, padx=(0, 12), sticky=tk.W); c += 1

        # Mensalidade (autoformatação)
        e_fee = ttk.Entry(row_top, textvariable=self.var_monthly_fee, width=24)
        e_fee.grid(row=1, column=c, padx=(0, 0), sticky=tk.W)
        self.attach_money_autofmt(e_fee, self.var_monthly_fee)

        # ===== Linha seguinte: Como conheceu / Para quem é / Atendido por =====
        row_mid = ttk.Frame(form)
        row_mid.pack(fill=tk.X, pady=6)

        ttk.Label(row_mid, text="Como conheceu a unidade").grid(row=0, column=0, sticky=tk.W)
        how_cb = ttk.Combobox(
            row_mid, textvariable=self.var_how_found, values=[
                "Indicação", "Google", "Instagram", "Facebook", "WhatsApp", "Ligação",
                "Outdoor", "Passagem/Frente da unidade", "Outros"
            ], width=28, state="readonly"
        )
        how_cb.grid(row=1, column=0, padx=(0,12), sticky=tk.W)

        ttk.Label(row_mid, text="Para quem é o curso").grid(row=0, column=1, sticky=tk.W)
        for_cb = ttk.Combobox(
            row_mid, textvariable=self.var_course_for, values=[
                "Próprio", "Filho(a)", "Neto(a)", "Sobrinho(a)", "Parceiro(a)", "Outro"
            ], width=22, state="readonly"
        )
        for_cb.grid(row=1, column=1, padx=(0,12), sticky=tk.W)

        ttk.Label(row_mid, text="Atendido por").grid(row=0, column=2, sticky=tk.W)
        ttk.Entry(row_mid, textvariable=self.var_attended_by, width=25)\
            .grid(row=1, column=2, padx=(0,0), sticky=tk.W)

        # ===== Observações: metade da altura =====
        notes_block = ttk.LabelFrame(self, text="Observações", padding=(10, 6))
        notes_block.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0,10))

        notes_inner = ttk.Frame(notes_block)
        notes_inner.pack(fill=tk.BOTH, expand=True)

        self.txt_notes = tk.Text(notes_inner, height=NOTES_DEFAULT_HEIGHT, wrap="word")
        self.txt_notes.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        notes_scroll = ttk.Scrollbar(notes_inner, orient="vertical", command=self.txt_notes.yview)
        notes_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.txt_notes.configure(yscrollcommand=notes_scroll.set)

        # ===== Botões =====
        btns = ttk.Frame(self)
        btns.pack(fill=tk.X, pady=(0, 10), padx=10)
        ttk.Button(btns, text="Novo / Limpar", command=self.clear_form).pack(side=tk.LEFT)
        ttk.Button(btns, text="Salvar", command=self.save_contact).pack(side=tk.LEFT, padx=6)
        ttk.Button(btns, text="Atualizar selecionado", command=self.update_selected).pack(side=tk.LEFT, padx=6)
        ttk.Button(btns, text="Apagar selecionado", command=self.delete_selected).pack(side=tk.LEFT, padx=6)


    # --------------------- Tabela ---------------------
    def create_table(self):
        table_frame = ttk.Frame(self, padding=(10, 0, 10, 10))
        table_frame.pack(fill=tk.BOTH, expand=True)

        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        cols = [c[0] for c in COLUMNS]
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", selectmode="browse")
        self.tree.grid(row=0, column=0, sticky="nsew")

        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        vsb.grid(row=0, column=1, sticky="ns")

        hsb = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        hsb.grid(row=1, column=0, sticky="ew")

        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        widths = {
            "id": 60, "name": 220, "phone": 130, "email": 220, "course": 160,
            "visit_date": 130, "status": 160, "monthly_fee": 140,
            "how_found": 190, "course_for": 150, "attended_by": 150, "notes": 800
        }
        for key, label in COLUMNS:
            self.tree.heading(key, text=label, command=lambda k=key: self.sort_by(k, False))
            self.tree.column(key, width=widths.get(key, 120), anchor=tk.W)

        self.tree.bind("<Double-1>", self.on_double_click)

    # --------------------- Eventos / Filtros ---------------------
    def bind_events(self):
        self.var_search.trace_add("write", lambda *args: self.refresh_table())
        self.var_filter_phone.trace_add("write", lambda *args: self.refresh_table())
        self.cb_att.bind("<<ComboboxSelected>>", lambda e: self.refresh_table())
        self.cb_course.bind("<<ComboboxSelected>>", lambda e: self.refresh_table())
        self.cb_status.bind("<<ComboboxSelected>>", lambda e: self.refresh_table())

    def clear_search(self):
        self.var_search.set("")

    def clear_filters(self):
        self.var_search.set("")
        self.var_filter_phone.set("")
        self.var_filter_att.set("Todos")
        self.var_filter_course.set("Todos")
        self.var_filter_status.set("Todos")
        self.var_filter_from.set("")
        self.var_filter_to.set("")
        self.refresh_table()

    def clear_form(self):
        self.var_name.set("")
        self.var_phone.set("")
        self.var_email.set("")
        self.var_course.set("")
        self.var_visit_date.set(datetime.date.today().strftime(DATE_FMT))
        self.var_status.set("Novo")
        self.var_monthly_fee.set("")
        self.var_how_found.set("Indicação")
        self.var_course_for.set("Próprio")
        self.var_attended_by.set("")
        if hasattr(self, "txt_notes"):
            self.txt_notes.delete("1.0", tk.END)

    # --------------------- DB helpers ---------------------
    def get_conn(self):
        return sqlite3.connect(DB_FILE)

    def refresh_filter_options(self):
        """Preenche combos de filtros (agora 'Curso' é padronizado, não vem do banco)."""
        con = self.get_conn()
        cur = con.cursor()

        def distinct_values(column):
            try:
                cur.execute(
                    f"SELECT DISTINCT {column} FROM contacts "
                    f"WHERE {column} IS NOT NULL AND {column} <> '' ORDER BY {column}"
                )
                return [r[0] for r in cur.fetchall() if r[0]]
            except sqlite3.OperationalError:
                return []

        self.cb_att["values"] = ["Todos"] + distinct_values("attended_by")
        # Curso padronizado:
        self.cb_course["values"] = ["Todos"] + COURSES
        self.cb_status["values"] = ["Todos"] + distinct_values("status")

        con.close()

    def ddmmyyyy_to_iso(self, s):
        """Converte DD/MM/AAAA (ou 8 dígitos) -> YYYY-MM-DD; retorna None se inválida."""
        s = (s or "").strip()
        if not s:
            return None
        norm = format_ddmmyyyy_from_digits(s)
        if norm:
            s = norm
        try:
            d = datetime.datetime.strptime(s, "%d/%m/%Y").date()
            return d.strftime("%Y-%m-%d")
        except ValueError:
            return None

    def build_filters(self):
        where = []
        params = []

        q = self.var_search.get().strip()
        if q:
            where.append("name LIKE ?")
            params.append(f"%{q}%")

        phone_q = re.sub(r"\D", "", self.var_filter_phone.get() or "")
        if phone_q:
            phone_digits_expr = ("replace(replace(replace(replace(replace(replace("
                                 "phone,'(',''),')',''),'-',''),' ',''),'.',''),'+','')")
            where.append(f"{phone_digits_expr} LIKE ?")
            params.append(f"%{phone_q}%")

        if self.var_filter_att.get() and self.var_filter_att.get() != "Todos":
            where.append("attended_by = ?")
            params.append(self.var_filter_att.get())

        if self.var_filter_course.get() and self.var_filter_course.get() != "Todos":
            where.append("course = ?")
            params.append(self.var_filter_course.get())

        if self.var_filter_status.get() and self.var_filter_status.get() != "Todos":
            where.append("status = ?")
            params.append(self.var_filter_status.get())

        vfrom_iso = self.ddmmyyyy_to_iso(self.var_filter_from.get())
        vto_iso = self.ddmmyyyy_to_iso(self.var_filter_to.get())

        visit_iso_expr = "(substr(visit_date,7,4)||'-'||substr(visit_date,4,2)||'-'||substr(visit_date,1,2))"

        if vfrom_iso and vto_iso:
            where.append(f"{visit_iso_expr} BETWEEN ? AND ?")
            params.extend([vfrom_iso, vto_iso])
        elif vfrom_iso:
            where.append(f"{visit_iso_expr} >= ?")
            params.append(vfrom_iso)
        elif vto_iso:
            where.append(f"{visit_iso_expr} <= ?")
            params.append(vto_iso)

        clause = (" WHERE " + " AND ".join(where)) if where else ""
        return clause, params

    def refresh_table(self):
        # Validação rápida das datas de filtro
        for label, v in [("Visita (De)", self.var_filter_from.get().strip()),
                         ("Visita (Até)", self.var_filter_to.get().strip())]:
            if v and self.ddmmyyyy_to_iso(v) is None:
                messagebox.showerror("Erro", "Data inválida. Use dd/mm/aaaa (8 dígitos aceitos).")
                return

        # Limpa a tabela
        for item in self.tree.get_children():
            self.tree.delete(item)

        con = self.get_conn()
        cur = con.cursor()
        base_select = """
            SELECT id, name, phone, email, course, visit_date, status,
                   monthly_fee, how_found, course_for, attended_by, notes
            FROM contacts
        """
        clause, params = self.build_filters()
        cur.execute(base_select + clause + " ORDER BY id DESC", params)
        for row in cur.fetchall():
            self.tree.insert("", tk.END, values=row)
        con.close()

    # --------------------- Anexadores de autoformatação ---------------------
    def attach_date_autofmt(self, entry_widget, var: tk.StringVar):
        def on_keyrelease(_ev=None):
            digits = _only_digits(var.get())
            if len(digits) == 8:
                fmt = format_ddmmyyyy_from_digits(digits)
                if fmt and fmt != var.get():
                    var.set(fmt)

        def on_focusout(_ev=None):
            text = (var.get() or "").strip()
            if not text:
                return
            fmt = format_ddmmyyyy_from_digits(text) or text
            iso = self.ddmmyyyy_to_iso(fmt)
            if iso:
                d = datetime.datetime.strptime(iso, "%Y-%m-%d").date()
                var.set(d.strftime("%d/%m/%Y"))

        entry_widget.bind("<KeyRelease>", on_keyrelease)
        entry_widget.bind("<FocusOut>", on_focusout)

    def attach_money_autofmt(self, entry_widget, var: tk.StringVar):
        def on_focusout(_ev=None):
            s = (var.get() or "").strip()
            if not s:
                return
            s = s.replace("R$", "").strip()
            digits = _only_digits(s)
            if digits.isdigit() and len(digits) >= 1:
                if "," not in s and "." not in s:
                    if len(digits) == 1:
                        s = "0.0" + digits
                    elif len(digits) == 2:
                        s = "0." + digits
                    else:
                        s = f"{int(digits[:-2])}.{digits[-2:]}"
                else:
                    s = s.replace(".", "").replace(",", ".")
            try:
                val = float(s)
                var.set(f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            except Exception:
                pass
        entry_widget.bind("<FocusOut>", on_focusout)

    def attach_phone_autofmt(self, entry_widget, var: tk.StringVar):
        def normalize_and_set(fmt: str):
            # guarda posição do cursor para evitar “pulos”
            try:
                pos = entry_widget.index(tk.INSERT)
            except Exception:
                pos = None
            var.set(fmt)
            # manda o cursor pro fim (fica melhor para digitação)
            try:
                entry_widget.icursor(tk.END)
            except Exception:
                pass

        def on_keyrelease(_ev=None):
            # Só formata automaticamente quando chegar a 11 dígitos
            d = re.sub(r"\D", "", var.get() or "")
            if len(d) > 11:
                d = d[:11]
                fmt = format_br_phone_from_digits(d)
                if fmt:
                    normalize_and_set(fmt)
            elif len(d) == 11:
                fmt = format_br_phone_from_digits(d)
                if fmt and fmt != var.get():
                    normalize_and_set(fmt)
            # com 10 dígitos não formata agora (evita o bug)

        def on_focusout(_ev=None):
            # No foco-perdido, formatamos o que tiver (8, 9, 10 ou 11)
            fmt = format_br_phone_from_digits(var.get())
            if fmt and fmt != var.get():
                var.set(fmt)

        entry_widget.bind("<KeyRelease>", on_keyrelease)
        entry_widget.bind("<FocusOut>", on_focusout)

    # --------------------- Validação & CRUD ---------------------
    def validate_date_field(self, date_str, field_name):
        if not date_str:
            return True
        try:
            datetime.datetime.strptime(date_str, DATE_FMT)
            return True
        except ValueError:
            messagebox.showerror("Erro", f"{field_name} inválida.")
            return False

    def normalize_money(self, s):
        s = (s or "").strip()
        if not s:
            return ""
        s = s.replace("R$", "").strip()
        s = s.replace(".", "").replace(",", ".")
        try:
            val = float(s)
            return f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        except ValueError:
            messagebox.showwarning("Atenção", "Valor de mensalidade inválido. Ex: 224,50")
            return ""

    def _get_notes_text(self):
        return self.txt_notes.get("1.0", tk.END).strip() if hasattr(self, "txt_notes") else self.var_notes.get().strip()

    def save_contact(self):
        name = self.var_name.get().strip()
        if not name:
            messagebox.showwarning("Atenção", "O campo Nome é obrigatório.")
            return

        visit_date = self.var_visit_date.get().strip()
        if not self.validate_date_field(visit_date, "Data da visita"):
            return

        monthly_fee = self.normalize_money(self.var_monthly_fee.get())
        notes = self._get_notes_text()

        con = self.get_conn()
        cur = con.cursor()
        cur.execute(
            """
            INSERT INTO contacts (name, phone, email, course, visit_date, status,
                                  monthly_fee, how_found, course_for, attended_by, notes)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                name,
                self.var_phone.get().strip(),
                self.var_email.get().strip(),
                self.var_course.get().strip(),
                visit_date or None,
                self.var_status.get().strip(),
                monthly_fee,
                self.var_how_found.get().strip(),
                self.var_course_for.get().strip(),
                self.var_attended_by.get().strip(),
                notes,
            ),
        )
        con.commit()
        con.close()
        self.refresh_filter_options()
        self.refresh_table()
        self.clear_form()
        messagebox.showinfo("Sucesso", "Contato salvo com sucesso.")

    def on_double_click(self, event):
        item = self.tree.selection()
        if not item:
            return
        vals = self.tree.item(item, "values")
        (
            _id, name, phone, email, course, visit_date, status,
            monthly_fee, how_found, course_for, attended_by, notes
        ) = vals
        self.var_name.set(name)
        self.var_phone.set(phone)
        self.var_email.set(email)
        self.var_course.set(course)
        self.var_visit_date.set(visit_date or "")
        self.var_status.set(status or "Novo")
        self.var_monthly_fee.set(monthly_fee or "")
        self.var_how_found.set(how_found or "Indicação")
        self.var_course_for.set(course_for or "Próprio")
        self.var_attended_by.set(attended_by or "")
        if hasattr(self, "txt_notes"):
            self.txt_notes.delete("1.0", tk.END)
            self.txt_notes.insert(tk.END, notes or "")
        else:
            self.var_notes.set(notes or "")

    def get_selected_id(self):
        sel = self.tree.selection()
        if not sel:
            return None
        vals = self.tree.item(sel, "values")
        return vals[0]

    def update_selected(self):
        contact_id = self.get_selected_id()
        if not contact_id:
            messagebox.showwarning("Atenção", "Selecione um contato na tabela para atualizar.")
            return

        name = self.var_name.get().strip()
        if not name:
            messagebox.showwarning("Atenção", "O campo Nome é obrigatório.")
            return

        visit_date = self.var_visit_date.get().strip()
        if not self.validate_date_field(visit_date, "Data da visita"):
            return

        monthly_fee = self.normalize_money(self.var_monthly_fee.get())
        notes = self._get_notes_text()

        con = self.get_conn()
        cur = con.cursor()
        cur.execute(
            """
            UPDATE contacts
            SET name=?, phone=?, email=?, course=?, visit_date=?, status=?,
                monthly_fee=?, how_found=?, course_for=?, attended_by=?, notes=?
            WHERE id=?
            """,
            (
                name,
                self.var_phone.get().strip(),
                self.var_email.get().strip(),
                self.var_course.get().strip(),
                visit_date or None,
                self.var_status.get().strip(),
                monthly_fee,
                self.var_how_found.get().strip(),
                self.var_course_for.get().strip(),
                self.var_attended_by.get().strip(),
                notes,
                contact_id,
            ),
        )
        con.commit()
        con.close()
        self.refresh_filter_options()
        self.refresh_table()
        messagebox.showinfo("Sucesso", "Contato atualizado com sucesso.")

    def delete_selected(self):
        contact_id = self.get_selected_id()
        if not contact_id:
            messagebox.showwarning("Atenção", "Selecione um contato na tabela para apagar.")
            return
        if not messagebox.askyesno("Confirmar", "Tem certeza que deseja apagar este contato?"):
            return
        con = self.get_conn()
        cur = con.cursor()
        cur.execute("DELETE FROM contacts WHERE id=?", (contact_id,))
        con.commit()
        con.close()
        self.refresh_filter_options()
        self.refresh_table()
        self.clear_form()
        messagebox.showinfo("Removido", "Contato apagado.")

    # --------------------- Ordenação e Export ---------------------
    def sort_by(self, col, descending):
        data = [(self.tree.set(child, col), child) for child in self.tree.get_children('')]

        if col == "visit_date":
            def key(v):
                try:
                    d = datetime.datetime.strptime(v[0], DATE_FMT).date() if v[0] else datetime.date.min
                except Exception:
                    d = datetime.date.min
                return d
        elif col == "monthly_fee":
            def key(v):
                s = (v[0] or "").replace(".", "").replace(",", ".")
                try:
                    return float(s)
                except:
                    return 0.0
        elif col == "id":
            def key(v):
                try:
                    return int(v[0])
                except:
                    return 0
        else:
            def key(v):
                return (v[0] or "").lower()

        data.sort(key=key, reverse=descending)
        for index, (_, child) in enumerate(data):
            self.tree.move(child, '', index)
        self.tree.heading(col, command=lambda: self.sort_by(col, not descending))

    def export_csv(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
            title="Salvar lista como CSV"
        )
        if not path:
            return
        con = self.get_conn()
        cur = con.cursor()
        clause, params = self.build_filters()
        cur.execute(f"""
            SELECT id, name, phone, email, course, visit_date, status,
                   monthly_fee, how_found, course_for, attended_by, notes
            FROM contacts {clause} ORDER BY id DESC
        """, params)
        rows = cur.fetchall()
        con.close()
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow([label for _, label in COLUMNS])
            for r in rows:
                w.writerow(r)
        messagebox.showinfo("Exportado", f"Arquivo CSV salvo em:\n{path}")

    def show_about(self):
        messagebox.showinfo(
            "Sobre",
            "Follow-up System (v6.7)\n"
            "- Curso/Interesse via dropdown padronizado também nos filtros; Observações expansiva.\n"
            "- Datas DD/MM/AAAA com digitação livre (8 dígitos) e autoformatação de telefone/mensalidade.\n"
            "Armazena no arquivo contacts.db (SQLite) no mesmo diretório.\n"
            "Dica: clique nos títulos da tabela para ordenar."
        )

def main():
    init_db()
    app = App()
    app.clear_form()
    app.mainloop()

if __name__ == "__main__":
    main()
