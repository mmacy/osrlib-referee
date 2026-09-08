"""Shared helpers for the tests that drive a battle through the server tool functions."""

from osrlib.crawl.commands import BattleDeclaration

from osrlib_referee_mcp.server import observe


def battle_round_declarations(group_id: str) -> tuple[BattleDeclaration, ...]:
    """Build one accepted declaration per declarer: the front rank attacks, the rest hold.

    A round must name exactly the members `observe`'s `encounter.declarers` lists, or it
    rejects whole (`battle.declaration.roster_mismatch`); a melee attack declared for
    anyone outside `encounter.front_rank` rejects too
    (`battle.declaration.not_in_front_rank`). Formation width follows the space the party
    stands in, so a test cannot assume the whole party can swing — it reads both rosters.

    Args:
        group_id: The target group for the front rank's attacks.

    Returns:
        The round's declarations, in declarer order.
    """
    encounter = observe()["encounter"]
    front_rank = set(encounter["front_rank"])
    return tuple(
        BattleDeclaration(character_id=character_id, action="attack", target_group_id=group_id)
        if character_id in front_rank
        else BattleDeclaration(character_id=character_id, action="hold")
        for character_id in encounter["declarers"]
    )
