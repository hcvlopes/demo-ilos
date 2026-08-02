"""Migration 002 — AcaoPermitida e Papel.

Delta 0.G: adiciona indices para AcaoPermitida e Papel.
Idempotente: ignora erro se indice ja existe.
"""

from db.adapter import create_driver


NOVOS_LABELS = ["AcaoPermitida", "Papel"]


def migrate(uri: str = None, user: str = None, password: str = None) -> None:
    driver = create_driver()

    with driver.session() as session:
        for label in NOVOS_LABELS:
            try:
                session.run(f"CREATE INDEX FOR (n:{label}) ON (n.id)")
            except Exception:
                pass

    driver.close()
    print(f"Migration 002 concluida. {len(NOVOS_LABELS)} indices adicionados.")


if __name__ == "__main__":
    migrate()
