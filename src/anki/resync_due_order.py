"""Reescribe `due` (posición en la cola de tarjetas NUEVAS) para que
coincida con el orden de `SortKey` — automatiza lo que antes se hacía a
mano en el Browser (ordenar por SortKey, Ctrl+A, Cards -> Reposition).

Por qué hace falta: Anki asigna `due` de forma secuencial al MOMENTO de
crear la nota (ver project_card_ordering), no según ningún campo de la
nota — así que una tarjeta agregada suelta después del export en bloque
(ej. una corrección puntual con `manual-card`, o para diagnosticar un
error real) queda al final de la cola aunque su `SortKey` diga que debería
ir intercalada por frecuencia. Confirmado en vivo: los valores de `due`
son ENTEROS DENSOS (sin huecos) dentro del mazo, así que insertar una sola
tarjeta en su lugar exige renumerar el resto — no hay un entero libre
"entre medio".

Solo toca tarjetas en queue=0 (nuevas, nunca repasadas) — para cualquier
otra, `due` significa una fecha/intervalo de repaso, NO una posición, y
tocarlo ahí sería un error real, no una optimización de orden."""

import argparse

from src.anki.api import post
from src.anki.export import deck_name_for

NEW_QUEUE = 0
RESYNC_BATCH_SIZE = 200


def resync_due_order(hsk_level: int = 3, dry_run: bool = True) -> dict:
    deck_name = deck_name_for(hsk_level)
    card_ids = post("findCards", query=f'deck:"{deck_name}"')
    info = post("cardsInfo", cards=card_ids)

    new_cards = [c for c in info if c["queue"] == NEW_QUEUE]
    skipped_reviewed = len(info) - len(new_cards)

    new_cards.sort(key=lambda c: c["fields"]["SortKey"]["value"])

    mismatches = [
        {"cardId": c["cardId"], "current_due": c["due"], "target_due": i, "hanzi": c["fields"]["Hanzi"]["value"]}
        for i, c in enumerate(new_cards)
        if c["due"] != i
    ]

    fixed = 0
    if not dry_run and mismatches:
        for i in range(0, len(mismatches), RESYNC_BATCH_SIZE):
            batch = mismatches[i:i + RESYNC_BATCH_SIZE]
            actions = [
                {
                    "action": "setSpecificValueOfCard",
                    "params": {"card": m["cardId"], "keys": ["due"], "newValues": [m["target_due"]], "warning_check": True},
                }
                for m in batch
            ]
            post("multi", actions=actions)
            fixed += len(batch)

    return {
        "checked": len(new_cards),
        "skipped_reviewed": skipped_reviewed,
        "mismatches": mismatches,
        "fixed": fixed,
        "dry_run": dry_run,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reescribe due para que coincida con el orden de SortKey (solo tarjetas nuevas)")
    parser.add_argument("--hsk-level", type=int, default=3)
    parser.add_argument("--apply", action="store_true", help="Aplica los cambios de verdad (default: dry-run, solo muestra qué cambiaría)")
    args = parser.parse_args()

    result = resync_due_order(hsk_level=args.hsk_level, dry_run=not args.apply)
    print(f"Tarjetas nuevas revisadas: {result['checked']}  (omitidas por ya estar en repaso: {result['skipped_reviewed']})")
    print(f"Fuera de orden: {len(result['mismatches'])}")
    for m in result["mismatches"][:20]:
        print(f"  {m['hanzi']}: due {m['current_due']} -> {m['target_due']}")
    if len(result["mismatches"]) > 20:
        print(f"  ... y {len(result['mismatches']) - 20} más")

    if result["dry_run"]:
        if result["mismatches"]:
            print("\nDry-run — nada se escribió. Corre con --apply para aplicar de verdad.")
    else:
        print(f"\nCorregidas: {result['fixed']}")
