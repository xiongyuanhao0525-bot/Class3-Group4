# -*- coding: utf-8 -*-
"""清除表格所有单元格的竖排 textDirection，恢复横排。"""
from docx import Document
from docx.oxml.ns import qn

TARGET = r'C:\Users\16570\Class3-Group4\doc\开源软件质量分析报告-DjangoBlog.docx'
doc = Document(TARGET)
removed = 0
for table in doc.tables:
    for row in table.rows:
        for tc in row._tr.findall(qn('w:tc')):
            tcPr = tc.find(qn('w:tcPr'))
            if tcPr is not None:
                td = tcPr.find(qn('w:textDirection'))
                if td is not None:
                    tcPr.remove(td)
                    removed += 1
doc.save(TARGET)
print('removed textDirection:', removed)
