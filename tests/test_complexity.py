"""`factory complexity`: complejidad por función, rangos, delta frente a REF y umbral."""

from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path

import pytest
from conftest import init_git_repo

from factory.cli import main
from factory.complexity import analizar, medir, rango


def _medidas(fuente: str) -> dict[str, int]:
    return {f.nombre: f.complejidad for f in medir(textwrap.dedent(fuente))}


def _escribir(root: Path, archivos: dict[str, str]) -> None:
    for ruta, fuente in archivos.items():
        destino = root / ruta
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(textwrap.dedent(fuente), encoding="utf-8")


def _commit(root: Path, mensaje: str = "cambio") -> None:
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", mensaje], cwd=root, check=True)


def _cli(root: Path, capsys, *args: str) -> tuple[int, str, str]:
    code = main(["--root", str(root), "complexity", *args])
    salida = capsys.readouterr()
    return code, salida.out, salida.err


def _json(root: Path, capsys, *args: str) -> tuple[int, dict]:
    code, out, _ = _cli(root, capsys, *args, "--json")
    return code, json.loads(out)


def _con_ifs(nombre: str, ifs: int) -> str:
    cuerpo = "".join(f"    if x == {i}:\n        return {i}\n" for i in range(ifs))
    return f"def {nombre}(x):\n{cuerpo}    return -1\n"


def _repo(tmp_path: Path, archivos: dict[str, str]) -> Path:
    root = init_git_repo(tmp_path / "repo")
    _escribir(root, archivos)
    _commit(root, "base")
    return root


# --- Cálculo -------------------------------------------------------------------------------


def test_funcion_lineal():
    assert _medidas("def f(a):\n    b = a + 1\n    return b\n") == {"f": 1}


def test_ramas_y_operadores_logicos():
    fuente = """
    def f(a, b, c, items):
        if a and b or c:
            pass
        elif a:
            pass
        for item in items:
            print(item)
    """
    assert _medidas(fuente) == {"f": 6}


def test_rango_de_una_funcion_lineal():
    (funcion,) = medir("def f():\n    return 1\n")
    assert funcion.complejidad == 1
    assert funcion.rango == "A"


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [(1, "A"), (5, "A"), (6, "B"), (10, "B"), (11, "C"), (20, "C"), (21, "D"), (30, "D")]
    + [(31, "E"), (40, "E"), (41, "F"), (100, "F")],
)
def test_limites_de_los_rangos(valor, esperado):
    assert rango(valor) == esperado


def test_metodo_de_una_clase():
    fuente = """
    class Motor:
        def arrancar(self):
            return True
    """
    assert _medidas(fuente) == {"Motor.arrancar": 1}


def test_funcion_anidada():
    fuente = """
    def externa(a):
        if a:
            pass

        def interna(b):
            if b:
                pass
            if not b:
                pass

        return interna
    """
    assert _medidas(fuente) == {"externa": 2, "externa.interna": 3}


def test_funcion_anidada_en_un_metodo_se_nombra_con_la_clase():
    fuente = """
    class Motor:
        def arrancar(self):
            def chispa():
                return 1
            return chispa
    """
    assert _medidas(fuente) == {"Motor.arrancar": 1, "Motor.arrancar.chispa": 1}


def test_match_suma_cada_case_incluido_el_comodin():
    fuente = """
    def f(orden):
        match orden:
            case "a":
                return 1
            case "b" | "c":
                return 2
            case _:
                return 3
    """
    assert _medidas(fuente) == {"f": 4}


def test_comprensiones_suman_cada_for_e_if():
    fuente = """
    def f(a, b):
        lista = [x for x in a if x if x > 1 for y in b]
        conjunto = {x for x in a}
        dic = {x: y for x, y in b if y}
        return sum(x for x in a), lista, conjunto, dic
    """
    # lista: 2 for + 2 if; conjunto: 1 for; dic: 1 for + 1 if; generador: 1 for
    assert _medidas(fuente) == {"f": 1 + 4 + 1 + 2 + 1}


def test_try_except_suma_cada_except():
    fuente = """
    def f():
        try:
            pass
        except ValueError:
            pass
        except (KeyError, TypeError):
            pass
        else:
            pass
        finally:
            pass
    """
    assert _medidas(fuente) == {"f": 3}


def test_while_async_for_y_expresion_condicional():
    fuente = """
    async def f(fuente, n):
        while n:
            n -= 1
        async for item in fuente:
            print(item)
        return 1 if n else 0
    """
    assert _medidas(fuente) == {"f": 4}


def test_lambda_asignada_a_un_nombre_se_mide_aparte():
    fuente = """
    def externa(a):
        signo = lambda x: 1 if x > 0 else -1
        return signo(a)

    doble = lambda x: x * 2 if x else 0
    """
    assert _medidas(fuente) == {"externa": 1, "externa.signo": 2, "doble": 2}


def test_lambda_anonima_suma_a_su_funcion():
    fuente = """
    def f(items):
        a = b = lambda x: x if x else 0
        return sorted(items, key=lambda x: x or 0), a, b
    """
    # +1 por la condicional de la lambda doble destino y +1 por el `or` de la anónima
    assert _medidas(fuente) == {"f": 3}


def test_codigo_de_modulo_y_cuerpo_de_clase_no_se_miden():
    fuente = """
    import os

    if os.name == "nt":
        SEP = "\\\\"
    VALORES = [x for x in range(3) if x]

    class Config:
        if VALORES:
            modo = "a"
        otro = 1 if VALORES else 2

        def leer(self):
            return self.modo
    """
    assert _medidas(fuente) == {"Config.leer": 1}


def test_decoradores_y_valores_por_defecto_suman_al_ambito_que_los_contiene():
    fuente = """
    def externa(a, b):
        @deco(a or b)
        def interna(x=a if b else 0):
            return x

        signo = lambda y=(a or 1): y
        return interna, signo
    """
    # externa: base 1 + `or` del decorador + condicional del defecto + `or` del defecto de la lambda
    assert _medidas(fuente) == {"externa": 4, "externa.interna": 1, "externa.signo": 1}


def test_arbol_muy_profundo_no_agota_la_recursion():
    cadena = " + ".join(["1"] * 600)
    ramas = "".join(f"    elif x == {i}:\n        return {i}\n" for i in range(400))
    fuente = f"X = {cadena}\n\ndef f(x):\n    y = {cadena}\n    if x:\n        return y\n{ramas}"
    assert _medidas(fuente) == {"f": 402}


def test_decisiones_de_una_funcion_anidada_no_suman_a_la_externa():
    fuente = """
    def externa(a):
        def interna(b):
            return [x for x in b if x and a]
        return interna
    """
    assert _medidas(fuente) == {"externa": 1, "externa.interna": 4}


# --- Alcance y salida ----------------------------------------------------------------------


def test_directorio_indicado(tmp_path, monkeypatch, capsys):
    root = tmp_path / "repo"
    _escribir(
        root,
        {
            "src/a.py": _con_ifs("media", 3) + "\n" + _con_ifs("alta", 7),
            "src/sub/b.py": "def baja():\n    return 1\n",
            "tests/test_a.py": _con_ifs("test_muy_alta", 20),
        },
    )
    monkeypatch.chdir(root)
    code, out, _ = _cli(root, capsys, "src")
    assert code == 0
    lineas = [linea for linea in out.splitlines() if linea[:1] in "ABCDEF" and linea[1:2] == " "]
    nombres = [linea.split()[3] for linea in lineas]
    assert nombres == ["alta", "media", "baja"]
    assert "test_muy_alta" not in out
    assert lineas[0].split()[:3] == ["B", "8", "src/a.py:10"]
    assert "Resumen: 3 función(es) · media 4.3 · máximo 8" in out


def test_directorio_excluye_ocultos_venv_y_pycache(tmp_path, monkeypatch, capsys):
    root = tmp_path / "repo"
    _escribir(
        root,
        {
            "pkg/ok.py": "def visible():\n    return 1\n",
            "pkg/.oculto/x.py": "def oculta():\n    return 1\n",
            "pkg/.venv/y.py": "def entorno():\n    return 1\n",
            "pkg/__pycache__/z.py": "def cache():\n    return 1\n",
        },
    )
    monkeypatch.chdir(root)
    _, datos = _json(root, capsys, "pkg")
    assert [f["nombre"] for f in datos["funciones"]] == ["visible"]


def test_sin_rutas_usa_los_archivos_versionados(tmp_path, capsys):
    root = _repo(tmp_path, {"src/a.py": "def versionada():\n    return 1\n"})
    _escribir(root, {"src/b.py": "def sin_versionar():\n    return 1\n"})
    _, datos = _json(root, capsys)
    assert [(f["archivo"], f["nombre"]) for f in datos["funciones"]] == [("src/a.py", "versionada")]


def test_sin_git_recorre_el_arbol_con_exclusiones(tmp_path, capsys):
    root = tmp_path / "sin-git"
    _escribir(
        root,
        {
            "a.py": "def uno():\n    return 1\n",
            "pkg/b.py": "def dos():\n    return 1\n",
            ".venv/lib/c.py": "def entorno():\n    return 1\n",
            ".git-falso/d.py": "def oculta():\n    return 1\n",
            "pkg/__pycache__/e.py": "def cache():\n    return 1\n",
        },
    )
    _, datos = _json(root, capsys)
    assert sorted(f["archivo"] for f in datos["funciones"]) == ["a.py", "pkg/b.py"]


def test_archivo_con_error_de_sintaxis(tmp_path, monkeypatch, capsys):
    root = tmp_path / "repo"
    _escribir(
        root,
        {"src/roto.py": "def f(:\n    pass\n", "src/sano.py": "def sana():\n    return 1\n"},
    )
    monkeypatch.chdir(root)
    code, out, err = _cli(root, capsys, "src")
    assert code == 0
    assert "aviso: src/roto.py" in err
    assert "sana" in out
    _, datos = _json(root, capsys, "src")
    assert [f["nombre"] for f in datos["funciones"]] == ["sana"]
    assert len(datos["avisos"]) == 1 and "src/roto.py" in datos["avisos"][0]


def test_ruta_inexistente_es_error_de_uso(tmp_path, monkeypatch, capsys):
    root = tmp_path / "repo"
    root.mkdir()
    monkeypatch.chdir(root)
    code, _, err = _cli(root, capsys, "no-existe")
    assert code == 2
    assert "no existe la ruta: no-existe" in err


def test_salida_json_con_las_claves_acordadas(tmp_path, monkeypatch, capsys):
    root = tmp_path / "repo"
    _escribir(root, {"m.py": _con_ifs("alta", 12) + "\ndef baja():\n    return 1\n"})
    monkeypatch.chdir(root)
    code, datos = _json(root, capsys, "m.py", "--max", "10")
    assert code == 1
    assert set(datos) == {"funciones", "resumen", "avisos", "umbral", "superan"}
    assert datos["umbral"] == 10
    assert datos["avisos"] == []
    assert datos["resumen"] == {"funciones": 2, "media": 7.0, "maximo": 13}
    primera = datos["funciones"][0]
    assert primera == {
        "archivo": "m.py",
        "linea": 1,
        "nombre": "alta",
        "complejidad": 13,
        "rango": "C",
        "base": None,
        "delta": None,
        "nueva": False,
    }
    assert [f["nombre"] for f in datos["superan"]] == ["alta"]


def test_sin_max_termina_en_cero_aunque_haya_funciones_complejas(tmp_path, monkeypatch, capsys):
    root = tmp_path / "repo"
    _escribir(root, {"m.py": _con_ifs("enorme", 45)})
    monkeypatch.chdir(root)
    code, out, _ = _cli(root, capsys, "m.py")
    assert code == 0
    assert out.startswith("F  46  m.py:1  enorme")


# --- Delta frente a una referencia ---------------------------------------------------------


def test_funcion_empeorada(tmp_path, capsys):
    root = _repo(tmp_path, {"src/m.py": _con_ifs("calcular", 3)})
    _escribir(root, {"src/m.py": _con_ifs("calcular", 5)})
    code, out, _ = _cli(root, capsys, "--base", "HEAD")
    assert code == 0
    assert "src/m.py:1  calcular  (base 4, +2)" in out
    _, datos = _json(root, capsys, "--base", "HEAD")
    (funcion,) = datos["funciones"]
    assert (funcion["base"], funcion["complejidad"], funcion["delta"]) == (4, 6, 2)
    assert funcion["nueva"] is False


def test_funcion_nueva(tmp_path, capsys):
    root = _repo(tmp_path, {"src/m.py": "def vieja():\n    return 1\n"})
    _escribir(
        root,
        {"src/m.py": "def vieja():\n    return 1\n\n\n" + _con_ifs("reciente", 2)},
    )
    code, out, _ = _cli(root, capsys, "--base", "HEAD")
    assert code == 0
    assert "reciente  (nueva)" in out
    assert "vieja  (base 1, +0)" in out
    _, datos = _json(root, capsys, "--base", "HEAD")
    reciente = next(f for f in datos["funciones"] if f["nombre"] == "reciente")
    assert reciente["nueva"] is True
    assert reciente["base"] is None and reciente["delta"] is None
    assert reciente["complejidad"] == 3


def test_base_incluye_los_no_versionados_y_omite_los_borrados(tmp_path, capsys):
    root = _repo(
        tmp_path,
        {
            "src/borrar.py": "def adios():\n    return 1\n",
            "src/igual.py": "def x():\n    return 1\n",
        },
    )
    (root / "src" / "borrar.py").unlink()
    _escribir(root, {"src/nuevo.py": "def hola():\n    return 1\n"})
    code, datos = _json(root, capsys, "--base", "HEAD")
    assert code == 0
    assert [(f["archivo"], f["nombre"], f["nueva"]) for f in datos["funciones"]] == [
        ("src/nuevo.py", "hola", True)
    ]


def test_base_con_rutas_filtra_los_cambiados(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, {"src/a.py": "def a():\n    return 1\n", "tests/t.py": "x = 1\n"})
    _escribir(root, {"src/a.py": _con_ifs("a", 1), "tests/t.py": "def t():\n    return 1\n"})
    monkeypatch.chdir(root)
    _, datos = _json(root, capsys, "src", "--base", "HEAD")
    assert [f["archivo"] for f in datos["funciones"]] == ["src/a.py"]


def test_duplicados_se_emparejan_por_orden(tmp_path):
    antes = textwrap.dedent(
        """\
        class C:
            @property
            def x(self):
                return 1

            @x.setter
            def x(self, v):
                if v:
                    pass
        """
    )
    despues = antes + "        if not v:\n            pass\n"
    root = _repo(tmp_path, {"m.py": antes})
    _escribir(root, {"m.py": despues})
    informe = analizar(root, base="HEAD")
    pares = sorted((f.linea, f.base, f.complejidad) for f in informe.funciones)
    assert not informe.avisos
    assert pares == [(3, 1, 1), (7, 2, 3)]


def test_base_con_version_previa_invalida_marca_las_funciones_como_nuevas(tmp_path, capsys):
    root = _repo(tmp_path, {"m.py": "def f(:\n"})
    _escribir(root, {"m.py": "def f():\n    return 1\n"})
    code, datos = _json(root, capsys, "--base", "HEAD")
    assert code == 0
    assert datos["funciones"][0]["nueva"] is True
    assert "HEAD" in datos["avisos"][0]


def test_base_invalida_es_error_de_uso(tmp_path, capsys):
    root = _repo(tmp_path, {"m.py": "def f():\n    return 1\n"})
    code, _, err = _cli(root, capsys, "--base", "no-existe")
    assert code == 2
    assert "referencia git inválida: no-existe" in err


def test_base_sin_git_es_error_de_uso(tmp_path, capsys):
    root = tmp_path / "sin-git"
    _escribir(root, {"m.py": "def f():\n    return 1\n"})
    code, _, err = _cli(root, capsys, "--base", "main")
    assert code == 2
    assert "requiere un repositorio git" in err


# --- Umbral --------------------------------------------------------------------------------


def test_umbral_superado(tmp_path, monkeypatch, capsys):
    root = tmp_path / "repo"
    _escribir(root, {"m.py": _con_ifs("compleja", 11) + "\ndef simple():\n    return 1\n"})
    monkeypatch.chdir(root)
    code, out, _ = _cli(root, capsys, "m.py", "--max", "10")
    assert code == 1
    assert "Superan el umbral 10: 1 función(es)" in out
    assert "  - m.py:1  compleja  (12)" in out
    assert "simple  (" not in out


def test_umbral_no_superado_termina_en_cero(tmp_path, monkeypatch, capsys):
    root = tmp_path / "repo"
    _escribir(root, {"m.py": _con_ifs("compleja", 11)})
    monkeypatch.chdir(root)
    code, out, _ = _cli(root, capsys, "m.py", "--max", "12")
    assert code == 0
    assert "Umbral 12: ninguna función lo supera." in out


def test_deuda_previa_sin_empeorar(tmp_path, capsys):
    root = _repo(tmp_path, {"m.py": _con_ifs("grande", 11) + "\n" + _con_ifs("chica", 1)})
    subprocess.run(["git", "switch", "-q", "-c", "rama"], cwd=root, check=True)
    _escribir(root, {"m.py": _con_ifs("grande", 11) + "\n" + _con_ifs("chica", 3)})
    _commit(root)
    code, datos = _json(root, capsys, "--base", "main", "--max", "10")
    assert code == 0
    grande = next(f for f in datos["funciones"] if f["nombre"] == "grande")
    assert (grande["complejidad"], grande["delta"]) == (12, 0)
    assert datos["superan"] == []


def test_umbral_con_base_cuenta_las_nuevas_y_las_empeoradas(tmp_path, capsys):
    root = _repo(tmp_path, {"m.py": _con_ifs("grande", 11)})
    _escribir(root, {"m.py": _con_ifs("grande", 12) + "\n" + _con_ifs("otra", 11)})
    code, out, _ = _cli(root, capsys, "--base", "HEAD", "--max", "10")
    assert code == 1
    assert "Superan el umbral 10: 2 función(es)" in out
    assert "m.py:1  grande  (13)" in out and "otra  (12)" in out


# --- Casos límite del alcance --------------------------------------------------------------


def test_renombrado_conserva_la_base(tmp_path, capsys):
    root = _repo(tmp_path, {"src/viejo.py": _con_ifs("deuda", 12)})
    subprocess.run(["git", "mv", "src/viejo.py", "src/nuevo.py"], cwd=root, check=True)
    code, datos = _json(root, capsys, "--base", "HEAD", "--max", "10")
    assert code == 0
    (funcion,) = datos["funciones"]
    assert (funcion["archivo"], funcion["base"], funcion["delta"]) == ("src/nuevo.py", 13, 0)
    assert funcion["nueva"] is False


def test_base_ignora_no_versionados_en_directorios_excluidos(tmp_path, capsys):
    root = _repo(tmp_path, {"src/a.py": "def a():\n    return 1\n"})
    _escribir(
        root,
        {
            "venvs/.venv/lib/x.py": "def tercero():\n    return 1\n",
            ".cache/y.py": "def oculta():\n    return 1\n",
            "src/__pycache__/z.py": "def cache():\n    return 1\n",
            "src/b.py": "def propia():\n    return 1\n",
        },
    )
    _, datos = _json(root, capsys, "--base", "HEAD")
    assert [f["nombre"] for f in datos["funciones"]] == ["propia"]


def test_ruta_fuera_del_repositorio_es_error_de_uso(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, {"m.py": "def f():\n    return 1\n"})
    _escribir(tmp_path / "otro", {"src/x.py": "def ajena():\n    return 1\n"})
    monkeypatch.chdir(tmp_path / "otro")
    for extra in ((), ("--base", "HEAD")):
        code, _, err = _cli(root, capsys, "src", *extra)
        assert code == 2
        assert "fuera del repositorio" in err


def test_la_ayuda_lista_el_subcomando(capsys):
    with pytest.raises(SystemExit):
        main(["--help"])
    assert "  complexity" in capsys.readouterr().out
