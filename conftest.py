# Este archivo, aunque esté vacío, hace que pytest añada la raíz del repo
# a sys.path. Sin él, `pytest tests/` falla al importar blitzbrief_bot y
# blitzhealth: solo funciona `python -m pytest`, que mete el directorio
# actual en sys.path por su cuenta. Así el comando documentado en
# CLAUDE.md y el de CI se comportan igual que en local.
