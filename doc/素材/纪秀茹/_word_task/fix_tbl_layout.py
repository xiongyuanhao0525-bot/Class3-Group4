# -*- coding: utf-8 -*-
"""将表格设为固定总宽（8862 twips）+ fixed 布局，强制列宽生效，消除竖排。"""
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

TARGET = r'C:\Users\16570\Class3-Group4\doc\开源软件质量分析报告-DjangoBlog.docx'
doc = Document(TARGET)
tbl = doc.tables[0]
tblPr = tbl._tbl.tblPr

# tblW -> dxa 8862
tblW = tblPr.find(qn('w:tblW'))
if tblW is None:
    tblW = OxmlElement('w:tblW')
    tblPr.append(tblW)
tblW.set(qn('w:w'), '8862')
tblW.set(qn('w:type'), 'dxa')

# tblLayout -> fixed，插到 tblCellMar / tblLook 之前（schema 顺序）
layout = tblPr.find(qn('w:tblLayout'))
if layout is None:
    layout = OxmlElement('w:tblLayout')
    anchor = tblPr.find(qn('w:tblCellMar'))
    if anchor is None:
        anchor = tblPr.find(qn('w:tblLook'))
    if anchor is not None:
        anchor.addprevious(layout)
    else:
        tblPr.append(layout)
layout.set(qn('w:type'), 'fixed')

doc.save(TARGET)
print('tblW/tblLayout set: fixed 8862')
