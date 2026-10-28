"""Verificación determinista: puntuación, timeout y firma de fallo normalizada."""

from factory.goal import Criterion
from factory.util import CommandResult
from factory.verify import Verification, normalize, run_criteria


def _v(**outputs):
    return Verification(
        {
            name: CommandResult(f"cmd-{name}", 0 if out is None else 1, out or "", 0.1)
            for name, out in outputs.items()
        }
    )


def test_puntuacion_y_criterios(tmp_path):
    criteria = [Criterion("ok", "true"), Criterion("falla", "echo uy; exit 2")]
    seen = []
    v = run_criteria(criteria, tmp_path, timeout_s=10, on_result=lambda n, r: seen.append(n))
    assert v.criteria == {"ok": True, "falla": False}
    assert (v.score, v.total, v.passed, v.failed) == (1, 2, False, ["falla"])
    assert seen == ["ok", "falla"]
    assert "❌ falla: `echo uy; exit 2` → código 2" in v.report() and "uy" in v.report()


def test_timeout(tmp_path):
    v = run_criteria([Criterion("lento", "sleep 5")], tmp_path, timeout_s=0.3)
    assert not v.passed and v.results["lento"].timed_out
    assert "tiempo agotado" in v.report()


def test_firma_estable_ante_numeros_rutas_y_hashes():
    fail = "FAILED tests/test_x.py::test_a - assert {} == {}\n/tmp/pytest-of-u/pytest-{}/x.py:{}\n"
    a = _v(tests=fail.format(3, 4, 12, 10) + "1 failed in 0.12s")
    b = _v(tests=fail.format(7, 9, 99, 33) + "1 failed in 4.50s")
    assert a.signature == b.signature != ""


def test_firma_distinta_ante_errores_distintos():
    a = _v(tests="FAILED tests/test_x.py::test_a - AssertionError")
    b = _v(tests="FAILED tests/test_x.py::test_b - KeyError")
    c = _v(lint="FAILED tests/test_x.py::test_a - AssertionError")
    assert len({a.signature, b.signature, c.signature}) == 3


def test_sin_fallos_firma_vacia():
    assert _v(tests=None).signature == ""


def test_normalize_quita_ansi_y_conserva_final():
    text = "\n".join(f"línea {i}" for i in range(40)) + "\n\x1b[31mERROR final\x1b[0m"
    out = normalize(text)
    assert out.endswith("ERROR final") and "línea N" in out and out.count("\n") == 14


def test_python_del_entorno_y_src_del_worktree(tmp_path):
    (tmp_path / "src" / "paquete_wt").mkdir(parents=True)
    (tmp_path / "src" / "paquete_wt" / "__init__.py").write_text("ORIGEN = 'worktree'\n")
    v = run_criteria(
        [
            Criterion(
                "import",
                "python -c 'import paquete_wt, yaml; assert paquete_wt.ORIGEN == \"worktree\"'",
            )
        ],
        tmp_path,
        timeout_s=30,
    )
    assert v.passed, v.report()
