from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Item:
    """Un producto visto en una fuente (web oficial o tienda)."""
    key: str                      # id único dentro de la fuente
    title: str
    url: str
    image: Optional[str] = None
    price: Optional[float] = None
    currency: str = "EUR"
    sku: Optional[str] = None
    status: str = "unknown"       # preorder | available | soldout | announced | news | unknown
    brand: Optional[str] = None
    extra_text: str = ""          # tags/categorías: solo para detectar marca/estado, no se guarda
    source: str = ""
    categories: str = ""          # categorías de la tienda, como "|slug|nombre|slug2|" (para filtrar por ellas)
    silent: bool = False          # guardar sin avisar (p. ej. posts viejos de una cuenta recién añadida)

    @property
    def uid(self) -> str:
        return f"{self.source}::{self.key}"


@dataclass
class Source:
    name: str
    platform: str                 # shopify | prestashop | woocommerce | minigt | auto
    url: str = ""
    kind: str = "retailer"        # official | retailer
    currency: str = "EUR"
    every_minutes: int = 60
    enabled: bool = True
    brands: list = field(default_factory=list)      # solo guarda estas marcas (vacío = todas las conocidas)
    default_brand: Optional[str] = None             # si no se detecta marca en el título
    preorder: bool = False                          # todo lo de esta fuente es preorder
    only_preorder: bool = False                     # solo avisa si el artículo está en preorder
    collection: Optional[str] = None                # shopify
    categories: list = field(default_factory=list)  # prestashop / woocommerce (urls o ids)
    searches: list = field(default_factory=list)    # woocommerce
    pages: list = field(default_factory=list)       # minigt
    max_pages: int = 3
    require: list = field(default_factory=list)     # regex: al menos una debe aparecer
    exclude: list = field(default_factory=list)     # regex: descarta si aparece
    section: Optional[str] = None                   # pestaña propia en el panel (clave de `sections:`)
    keep_all: bool = False                          # guardar TODO lo que salga (sin filtro de marca/escala)
    alert_all: bool = False                         # con keep_all: avisar también de lo que no es de tus marcas
    accounts: list = field(default_factory=list)    # instagram: cuentas a seguir
    options: dict = field(default_factory=dict)     # opciones propias de la plataforma

    @classmethod
    def from_dict(cls, d: dict) -> "Source":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})
