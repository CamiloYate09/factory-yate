"""La ayuda de `factory --help` lista todos los subcomandos del CLI."""

import argparse

import pytest

from factory.cli import build_parser, main

SUBCOMANDOS = [
    "init",
    "features",
    "goal",
    "inbox",
    "tick",
    "schedule",
    "intake",
    "brain",
    "team",
    "land",
    "status",
    "complexity",
    "doctor",
]


def test_ayuda_lista_todos_los_subcomandos(capsys):
    with pytest.raises(SystemExit) as salida:
        main(["--help"])
    assert salida.value.code == 0
    texto = capsys.readouterr().out
    faltan = [nombre for nombre in SUBCOMANDOS if f"  {nombre}" not in texto]
    assert not faltan, f"subcomandos ausentes en la ayuda: {faltan}"


def test_la_lista_cubre_todos_los_subcomandos_del_parser():
    """Un subcomando nuevo sin añadir aquí rompe este test: la lista no se queda atrás."""
    acciones = build_parser()._subparsers._group_actions
    [subparsers] = [a for a in acciones if isinstance(a, argparse._SubParsersAction)]
    assert set(subparsers.choices) == set(SUBCOMANDOS)
