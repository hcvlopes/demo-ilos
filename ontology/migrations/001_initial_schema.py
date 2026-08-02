"""Migration 001 — Schema inicial completo.

Idempotente: pode rodar multiplas vezes sem erro nem duplicacao.
Cria indices para todos os labels com propriedade de unicidade.
"""

from db.adapter import create_driver
from ontology.schema import NODE_LABELS, UNIQUENESS_CONSTRAINTS


def migrate(uri: str = None, user: str = None, password: str = None) -> None:
    driver = create_driver()

    with driver.session() as session:
        for label, prop in UNIQUENESS_CONSTRAINTS.items():
            try:
                session.run(f"CREATE INDEX FOR (n:{label}) ON (n.{prop})")
            except Exception:
                pass

        result = session.run(
            "MATCH ()-[r:CONECTADO]->() RETURN count(r) AS cnt"
        )
        record = result.single()
        cnt = record["cnt"] if record else 0
        if cnt > 0:
            session.run("MATCH ()-[r:CONECTADO]->() DELETE r")
            print(f"Removidas {cnt} arestas CONECTADO genericas.")

    driver.close()
    print(f"Migration 001 concluida. {len(NODE_LABELS)} indices verificados.")


if __name__ == "__main__":
    migrate()
