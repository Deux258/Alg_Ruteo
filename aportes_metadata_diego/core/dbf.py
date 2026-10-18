"""Lectores mínimos sin dependencias: tabla DBF (atributos de un ráster, .vat.dbf) y texto de metadatos XML."""
import xml.etree.ElementTree as ET


def leer_dbf(path):
    """Devuelve (nombres_de_campo, lista_de_filas_como_dict)."""
    with open(path, "rb") as f:
        h = f.read(32)
        n = int.from_bytes(h[4:8], "little")
        largo_cab = int.from_bytes(h[8:10], "little")
        largo_reg = int.from_bytes(h[10:12], "little")
        campos = []
        while True:
            d = f.read(32)
            if not d or d[0] == 0x0D:
                break
            campos.append((d[:11].split(b"\x00")[0].decode("latin-1"), d[11:12].decode("latin-1"), d[16]))
        f.seek(largo_cab)
        filas = []
        for _ in range(n):
            r = f.read(largo_reg)
            if not r or r[:1] == b"*":
                continue
            pos, fila = 1, {}
            for nombre, tipo, ln in campos:
                txt = r[pos:pos + ln].decode("latin-1").strip()
                pos += ln
                if tipo in "NF" and txt:
                    try:
                        txt = float(txt) if ("." in txt or "e" in txt.lower()) else int(txt)
                    except ValueError:
                        pass
                fila[nombre] = txt
            filas.append(fila)
    return [c[0] for c in campos], filas


def resumen_xml(path, max_chars=500):
    """Textos descriptivos (título, resumen, propósito...) de un .xml de metadatos."""
    claves = {"title", "restitle", "abstract", "idabs", "purpose", "idpurp", "supplinf", "descript"}
    salida = []
    try:
        for e in ET.parse(path).getroot().iter():
            tag = e.tag.split("}")[-1].lower()
            if tag in claves and e.text and e.text.strip():
                salida.append(f"  [{tag}] {' '.join(e.text.split())[:max_chars]}")
    except ET.ParseError:
        pass
    return salida
