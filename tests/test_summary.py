"""Escenario de `loop-state`: resumen acotado para la siguiente ronda."""

from factory.state import RoundRecord, RunState, build_summary


def _state(rounds=15):
    state = RunState(run_id="r", goal_id="largo", objective="o", best_round=6, best_score=3)
    for n in range(1, rounds + 1):
        state.rounds.append(
            RoundRecord(
                number=n,
                started="x",
                maker_summary=f"intento número {n} " + "detalle " * 40,
                criteria={"tests": n == 6, "lint": True, "tipos": n % 2 == 0},
                score=3 if n == 6 else 1,
                checker_verdict="fail",
                decision="revert" if n != 6 else "keep",
            )
        )
    state.blockers = ["el test de integración falla por timeout (rondas 10-15)"]
    return state


def test_ejecucion_larga_respeta_el_maximo_e_incluye_lo_prioritario():
    state = _state(15)
    summary = build_summary(state, max_chars=1500)
    assert len(summary) <= 1500
    assert "Bloqueos activos: el test de integración falla" in summary
    assert "Ronda más reciente: Ronda 15" in summary
    assert "Mejor ronda (estado actual de la rama): Ronda 6" in summary
    # Ronda 14 (la inmediatamente anterior) entra antes que rondas más antiguas.
    if "Ronda 1:" in summary:
        assert summary.index("Ronda 14:") < summary.index("Ronda 1:")
    assert "Anterior: Ronda 14" in summary


def test_resumen_no_crece_con_el_historial():
    short = build_summary(_state(15), max_chars=2000)
    long = build_summary(_state(60), max_chars=2000)
    assert len(long) <= 2000 and len(short) <= 2000


def test_resumen_sin_rondas():
    state = RunState(run_id="r", goal_id="g", objective="o")
    assert build_summary(state, 500) == "Estado del loop 'g' tras 0 ronda(s)."


def test_trunca_si_lo_prioritario_no_cabe():
    summary = build_summary(_state(3), max_chars=120)
    assert len(summary) <= 120 and summary.endswith("…")
