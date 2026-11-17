"""Расчёт весов офферов кампании.

Правила:
- сумма весов всегда 100;
- незакреплённые офферы делят остаток поровну (остаток по одному проценту сверху);
- закреплённый оффер сохраняет свой вес и не пересчитывается при добавлении и удалении других;
- если все офферы закреплены, их веса должны в сумме давать 100.
"""

TOTAL = 100


class WeightError(ValueError):
    """Веса нельзя распределить: сообщение пригодно для пользователя."""


def compute_shares(offer_ids: list[int], pinned: dict[int, int]) -> dict[int, int]:
    """Возвращает вес каждого оффера в порядке offer_ids. pinned: offer_id -> закреплённый вес."""
    if not offer_ids:
        return {}

    pinned_ids = [o for o in offer_ids if o in pinned]
    free_ids = [o for o in offer_ids if o not in pinned]
    pinned_sum = sum(pinned[o] for o in pinned_ids)

    if not free_ids:
        if pinned_sum != TOTAL:
            raise WeightError(
                f"Все офферы закреплены, их веса дают {pinned_sum}%. Сумма должна быть ровно {TOTAL}%."
            )
        return {o: pinned[o] for o in offer_ids}

    remaining = TOTAL - pinned_sum
    if remaining < len(free_ids):
        raise WeightError(
            f"Закреплённые веса занимают {pinned_sum}%, на {len(free_ids)} незакреплённых остаётся "
            f"{remaining}%. Уменьшите закреплённые веса или снимите закрепление."
        )

    base, extra = divmod(remaining, len(free_ids))
    shares: dict[int, int] = {}
    for i, o in enumerate(free_ids):
        shares[o] = base + (1 if i < extra else 0)
    shares.update({o: pinned[o] for o in pinned_ids})
    return {o: shares[o] for o in offer_ids}
