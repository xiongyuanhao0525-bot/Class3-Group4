# -*- coding: utf-8 -*-
"""从 3.3 第7条段落移除错误的段内 sectPr 分节符，使全文统一为 body 级分节。"""
import shutil
import zipfile
from lxml import etree
import os

CAND = r'C:\Users\16570\AppData\Local\Doubao\User Data\Default\DoubaoStorage\Aida\doubao-office\ai-edit\2B2EO7HaNFl3HHLAhd50GPpRXoW-1792824506708-9dl4vsxxlcm.docx'
SRC = r'C:\Users\16570\Class3-Group4\doc\素材\纪秀茹\_word_task\SOURCE_ooxml2.docx'
shutil.copy(CAND, SRC)

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
NS = {'w': W}
tmp = CAND + '.tmp'
with zipfile.ZipFile(CAND) as zin, zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zout:
    for item in zin.infolist():
        data = zin.read(item.filename)
        if item.filename == 'word/document.xml':
            root = etree.fromstring(data)
            body = root.find('w:body', NS)
            paras = body.findall('w:p', NS)
            removed = 0
            for i, para in enumerate(paras):
                pPr = para.find('w:pPr', NS)
                if pPr is not None:
                    sect = pPr.find('w:sectPr', NS)
                    if sect is not None:
                        pPr.remove(sect)
                        removed += 1
                        print('removed sectPr from para', i)
            data = etree.tostring(root, xml_declaration=True, encoding='UTF-8', standalone=True)
        zout.writestr(item, data)
os.replace(tmp, CAND)
print('done, removed total:', removed)
