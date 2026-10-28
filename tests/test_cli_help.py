"""La ayuda de `factory --help` lista todos los subcomandos del CLI."""

import pytest

from factory.cli import main

SUBCOMANDOS = ["init", "features", "goal", "inbox", "tick", "schedule", "status", "doctor"]


def test_ayuda_lista_todos_los_subcomandos(capsys):
    with pytest.raises(SystemExit) as salida:
        main(["--help"])
    assert salida.value.code == 0
    texto = capsys.readouterr().out
    faltan = [nombre for nombre in SUBCOMANDOS if f"  {nombre}" not in texto]
    assert not faltan, f"subcomandos ausentes en la ayuda: {faltan}"
