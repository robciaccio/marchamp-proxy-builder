"""Catalog entities (FR-005e, FR-005b, FR-005b1).

A Card is one title with one set of rules. A Printing is one pack's artwork for it. The
split exists because the same card is republished with pack-appropriate art, and a deck
should print with its own pack's version.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Printing(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    pack: str = Field(min_length=1)
    image: str = Field(min_length=1)
    image_back: str | None = None
    # Pack-scoped and informational only. Make the Call is 16 in the Captain America pack
    # and 71 in the Core Set, so a number can never identify a card.
    number: str | None = None


class Card(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    double_sided: bool = False
    printings: list[Printing] = Field(min_length=1)

    def printing(self, printing_id: str) -> Printing | None:
        return next((p for p in self.printings if p.id == printing_id), None)


class CardEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    card_id: str = Field(min_length=1)
    preferred_printing_id: str = Field(min_length=1)
    quantity: int


class HeroDeck(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    hero_card_id: str = Field(min_length=1)
    entries: list[CardEntry] = Field(min_length=1)


class Catalog(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str
    cards: list[Card]
    decks: list[HeroDeck]
    revision: str = ""

    def card(self, card_id: str) -> Card | None:
        return next((c for c in self.cards if c.id == card_id), None)

    def deck(self, deck_id: str) -> HeroDeck | None:
        return next((d for d in self.decks if d.id == deck_id), None)

    def card_of_printing(self, printing_id: str) -> Card | None:
        return next((c for c in self.cards if c.printing(printing_id) is not None), None)
