from __future__ import annotations

from typing import NewType

# Both are opaque strings of the same shape; distinct types stop one being passed for the other.
BookingId = NewType("BookingId", str)
# Our id for one payment attempt; the provider knows the attempt by it.
OrderId = NewType("OrderId", str)
