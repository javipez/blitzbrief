"""Comprobación de las opciones de línea de comandos de los scripts.

Sin esto, una opción mal escrita (`--preview-partido` sin la s) no daba
error: el script no la reconocía y se iba al caso por defecto, que es el
envío de verdad a Telegram. Mejor pararse y avisar.
"""

import difflib
import sys
from typing import Iterable


def reject_unknown_options(valid: Iterable[str], argv: list[str]) -> None:
    """Sale con un error si `argv` trae alguna opción que no está en `valid`.

    Si la opción se parece a una válida, sugiere cuál se quería escribir.
    Sale con código 2, el convenio para "se ha llamado mal al programa".
    """
    valid = list(valid)
    unknown = [arg for arg in argv if arg not in valid]
    if not unknown:
        return

    for arg in unknown:
        message = f"Opción desconocida: {arg}"
        close = difflib.get_close_matches(arg, valid, n=1)
        if close:
            message += f". ¿Querías decir {close[0]}?"
        print(message, file=sys.stderr)

    print("Opciones válidas: " + ", ".join(valid), file=sys.stderr)
    print("Sin opciones, el script hace el envío normal.", file=sys.stderr)
    sys.exit(2)
