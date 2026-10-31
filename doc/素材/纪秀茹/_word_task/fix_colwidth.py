# -*- coding: utf-8 -*-
"""统一重设表格所有单元格宽度为与 gridCol 一致的列宽，消除竖排。"""
from docx import Document
from docx.shared import Twips
from docx.oxml.ns import qn

TARGET = r'C:\Users\16570\Class3-Group4\doc\开源软件质量分析报告-DjangoBlog.docx'
WIDTHS = [1200, 1300, 3762, 2600]
doc = Document(TARGET)
for table in doc.tables:
    for row in table.rows:
        cells = row.cells[:4]
        for j, cell in enumerate(cells):
            try:
                cell.width = Twips(WIDTHS[j])
            except Exception as e:
                print('skip', j, e)
doc.save(TARGET)
print('cells resized:', len(doc.tables[0].rows) * 4)
