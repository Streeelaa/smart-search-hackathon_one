from datetime import datetime, timezone
from typing import Protocol

from app.catalog_loader import load_catalog
from app.db import SessionLocal, init_database
from app.db_models import EventRow, ProductRow
from app.settings import settings
from app.schemas import Event, EventCreate, Product, UserProfile


class RepositoryProtocol(Protocol):
    @property
    def products(self) -> list[Product]: ...

    def list_products(self, category: str | None = None) -> list[Product]: ...
    def get_product(self, item_id: int) -> Product | None: ...
    def add_event(self, payload: EventCreate) -> Event: ...
    def get_user_profile(self, user_id: str) -> UserProfile: ...
    def list_user_events(self, user_id: str) -> list[Event]: ...
    def replace_products(self, products: list[Product]) -> None: ...
    def replace_events(self, payloads: list[EventCreate]) -> None: ...
    def append_events(self, payloads: list[EventCreate]) -> None: ...
    def count_products(self) -> int: ...
    def count_events(self) -> int: ...
    def count_profiles(self) -> int: ...
    def backend_name(self) -> str: ...
    def reset_demo_state(self) -> None: ...


def demo_history() -> list[EventCreate]:
    return [
        EventCreate(user_id="user-1", event_type="search", query="ноутбук для офиса"),
        EventCreate(user_id="user-1", event_type="click", item_id=1),
        EventCreate(user_id="user-1", event_type="purchase", item_id=1),
        EventCreate(user_id="user-1", event_type="click", item_id=6),
        EventCreate(user_id="user-2", event_type="search", query="мфу hp"),
        EventCreate(user_id="user-2", event_type="purchase", item_id=2),
        EventCreate(user_id="user-2", event_type="click", item_id=5),
    ]


class InMemoryRepository:
    def __init__(self) -> None:
        self.products = load_catalog()
        self.events: list[Event] = []
        self.user_profiles: dict[str, UserProfile] = {}
        self._next_event_id = 1
        self._seed_demo_history()

    def _seed_demo_history(self) -> None:
        for event in demo_history():
            self.add_event(event)

    def list_products(self, category: str | None = None) -> list[Product]:
        if not category:
            return list(self.products)
        normalized = category.strip().lower()
        return [product for product in self.products if product.category.lower() == normalized]

    def get_product(self, item_id: int) -> Product | None:
        for product in self.products:
            if product.id == item_id:
                return product
        return None

    def add_event(self, payload: EventCreate) -> Event:
        event = Event(
            event_id=self._next_event_id,
            timestamp=datetime.now(timezone.utc),
            **payload.model_dump(),
        )
        self._next_event_id += 1
        self.events.append(event)
        self.user_profiles[event.user_id] = self._rebuild_profile(event.user_id)
        return event

    def replace_products(self, products: list[Product]) -> None:
        self.products = list(products)
        self._rebuild_all_profiles()

    def replace_events(self, payloads: list[EventCreate]) -> None:
        self.events = []
        self.user_profiles = {}
        self._next_event_id = 1
        for payload in payloads:
            self.add_event(payload)

    def append_events(self, payloads: list[EventCreate]) -> None:
        for payload in payloads:
            self.add_event(payload)

    def get_user_profile(self, user_id: str) -> UserProfile:
        return self.user_profiles.get(user_id) or self._rebuild_profile(user_id)

    def list_user_events(self, user_id: str) -> list[Event]:
        return [event for event in self.events if event.user_id == user_id]

    def _rebuild_profile(self, user_id: str) -> UserProfile:
        events = self.list_user_events(user_id)
        category_affinity: dict[str, float] = {}
        tag_affinity: dict[str, float] = {}
        recent_queries: list[str] = []
        purchased_prices: list[float] = []

        for event in events:
            if event.query:
                recent_queries.append(event.query)

            if event.item_id is None:
                continue

            product = self.get_product(event.item_id)
            if product is None:
                continue

            weight = {"click": 1.0, "favorite": 2.0, "purchase": 3.0}.get(event.event_type, 0.3)
            category_affinity[product.category] = category_affinity.get(product.category, 0.0) + weight

            for tag in product.tags:
                tag_affinity[tag] = tag_affinity.get(tag, 0.0) + weight

            if event.event_type == "purchase":
                purchased_prices.append(product.price)

        average_price = None
        if purchased_prices:
            average_price = sum(purchased_prices) / len(purchased_prices)

        profile = UserProfile(
            user_id=user_id,
            total_events=len(events),
            category_affinity=dict(sorted(category_affinity.items(), key=lambda item: item[1], reverse=True)[:5]),
            tag_affinity=dict(sorted(tag_affinity.items(), key=lambda item: item[1], reverse=True)[:10]),
            recent_queries=recent_queries[-5:],
            average_price=average_price,
        )
        self.user_profiles[user_id] = profile
        return profile

    def _rebuild_all_profiles(self) -> None:
        user_ids = {event.user_id for event in self.events}
        self.user_profiles = {}
        for user_id in user_ids:
            self._rebuild_profile(user_id)

    def count_products(self) -> int:
        return len(self.products)

    def count_events(self) -> int:
        return len(self.events)

    def count_profiles(self) -> int:
        return len(self.user_profiles)

    def backend_name(self) -> str:
        return "memory"

    def reset_demo_state(self) -> None:
        self.products = load_catalog()
        self.events = []
        self.user_profiles = {}
        self._next_event_id = 1
        self._seed_demo_history()


class SQLRepository:
    def __init__(self) -> None:
        init_database()
        if settings.seed_demo_data:
            self._seed_if_needed()

    @property
    def products(self) -> list[Product]:
        return self.list_products()

    def list_products(self, category: str | None = None) -> list[Product]:
        with SessionLocal() as session:
            query = session.query(ProductRow)
            if category:
                query = query.filter(ProductRow.category.ilike(category.strip()))
            rows = query.order_by(ProductRow.id.asc()).all()
            return [self._product_from_row(row) for row in rows]

    def get_product(self, item_id: int) -> Product | None:
        with SessionLocal() as session:
            row = session.get(ProductRow, item_id)
            return self._product_from_row(row) if row else None

    def add_event(self, payload: EventCreate) -> Event:
        with SessionLocal() as session:
            row = EventRow(
                user_id=payload.user_id,
                event_type=payload.event_type,
                item_id=payload.item_id,
                query=payload.query,
                event_metadata=payload.metadata,
                timestamp=datetime.now(timezone.utc),
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return self._event_from_row(row)

    def get_user_profile(self, user_id: str) -> UserProfile:
        events = self.list_user_events(user_id)
        return self._build_profile(user_id, events)

    def list_user_events(self, user_id: str) -> list[Event]:
        with SessionLocal() as session:
            rows = (
                session.query(EventRow)
                .filter(EventRow.user_id == user_id)
                .order_by(EventRow.timestamp.asc(), EventRow.event_id.asc())
                .all()
            )
            return [self._event_from_row(row) for row in rows]

    def replace_products(self, products: list[Product]) -> None:
        with SessionLocal() as session:
            session.query(ProductRow).delete()
            session.add_all([self._row_from_product(product) for product in products])
            session.commit()

    def replace_events(self, payloads: list[EventCreate]) -> None:
        with SessionLocal() as session:
            session.query(EventRow).delete()
            session.commit()
        self.append_events(payloads)

    def append_events(self, payloads: list[EventCreate]) -> None:
        with SessionLocal() as session:
            rows = [
                EventRow(
                    user_id=payload.user_id,
                    event_type=payload.event_type,
                    item_id=payload.item_id,
                    query=payload.query,
                    event_metadata=payload.metadata,
                    timestamp=datetime.now(timezone.utc),
                )
                for payload in payloads
            ]
            session.add_all(rows)
            session.commit()

    def count_products(self) -> int:
        with SessionLocal() as session:
            return int(session.query(ProductRow).count())

    def count_events(self) -> int:
        with SessionLocal() as session:
            return int(session.query(EventRow).count())

    def count_profiles(self) -> int:
        with SessionLocal() as session:
            return int(session.query(EventRow.user_id).distinct().count())

    def backend_name(self) -> str:
        return "sql"

    def reset_demo_state(self) -> None:
        self.replace_products(load_catalog())
        self.replace_events(demo_history())

    def _seed_if_needed(self) -> None:
        if self.count_products() == 0:
            self.replace_products(load_catalog())
        if self.count_events() == 0:
            self.append_events(demo_history())

    def _product_from_row(self, row: ProductRow) -> Product:
        return Product(
            id=row.id,
            sku=row.sku,
            title=row.title,
            category=row.category,
            description=row.description,
            price=row.price,
            tags=list(row.tags_json or []),
            aliases=list(row.aliases_json or []),
            attributes=dict(row.attributes_json or {}),
        )

    def _event_from_row(self, row: EventRow) -> Event:
        return Event(
            event_id=row.event_id,
            user_id=row.user_id,
            event_type=row.event_type,
            item_id=row.item_id,
            query=row.query,
            metadata=dict(row.event_metadata or {}),
            timestamp=row.timestamp,
        )

    def _row_from_product(self, product: Product) -> ProductRow:
        return ProductRow(
            id=product.id,
            sku=product.sku,
            title=product.title,
            category=product.category,
            description=product.description,
            price=product.price,
            tags_json=product.tags,
            aliases_json=product.aliases,
            attributes_json=product.attributes,
        )

    def _build_profile(self, user_id: str, events: list[Event]) -> UserProfile:
        category_affinity: dict[str, float] = {}
        tag_affinity: dict[str, float] = {}
        recent_queries: list[str] = []
        purchased_prices: list[float] = []

        product_map = {product.id: product for product in self.products}
        for event in events:
            if event.query:
                recent_queries.append(event.query)

            if event.item_id is None:
                continue

            product = product_map.get(event.item_id)
            if product is None:
                continue

            weight = {"click": 1.0, "favorite": 2.0, "purchase": 3.0}.get(event.event_type, 0.3)
            category_affinity[product.category] = category_affinity.get(product.category, 0.0) + weight
            for tag in product.tags:
                tag_affinity[tag] = tag_affinity.get(tag, 0.0) + weight
            if event.event_type == "purchase":
                purchased_prices.append(product.price)

        average_price = sum(purchased_prices) / len(purchased_prices) if purchased_prices else None
        return UserProfile(
            user_id=user_id,
            total_events=len(events),
            category_affinity=dict(sorted(category_affinity.items(), key=lambda item: item[1], reverse=True)[:5]),
            tag_affinity=dict(sorted(tag_affinity.items(), key=lambda item: item[1], reverse=True)[:10]),
            recent_queries=recent_queries[-5:],
            average_price=average_price,
        )


def create_repository() -> RepositoryProtocol:
    if settings.storage_backend == "sql":
        return SQLRepository()
    return InMemoryRepository()


repository: RepositoryProtocol = create_repository()