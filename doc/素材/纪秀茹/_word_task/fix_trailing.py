# -*- coding: utf-8 -*-
"""删除文档末尾尾随空段落，消除可能的空白末页。"""
import shutil
import zipfile
from lxml import etree
import os

CAND = r'C:\Users\16570\AppData\Local\Doubao\User Data\Default\DoubaoStorage\Aida\doubao-office\ai-edit\2B2EO7HaNFl3HHLAhd50GPpRXoW-1792824856555-fh24ao33pwh.docx'
SRC = r'C:\Users\16570\Class3-Group4\doc\素材\纪秀茹\_word_task\SOURCE_ooxml3.docx'
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
            # 最后一个 body 直接子节点若是空段则删除
            kids = list(body)
            removed = 0
            # body 级 sectPr 前的最后一个段若是空段则删除
            if kids and kids[-1].tag == '{%s}sectPr' % W:
                prev = kids[-2] if len(kids) >= 2 else None
                if prev is not None and prev.tag == '{%s}p' % W:
                    pPr = prev.find('w:pPr', NS)
                    has_sect = pPr is not None and pPr.find('w:sectPr', NS) is not None
                    txt = ''.join(t.text or '' for t in prev.findall('.//w:t', NS))
                    brs = prev.findall('.//w:br', NS)
                    if not txt.strip() and not has_sect and not brs:
                        body.remove(prev)
                        removed = 1
                        print('removed trailing empty para before sectPr')
            data = etree.tostring(root, xml_declaration=True, encoding='UTF-8', standalone=True)
        zout.writestr(item, data)
os.replace(tmp, CAND)
print('done, removed:', removed)
