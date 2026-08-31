from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

#: Starlette, `def` (async olmayan) uç noktaları kendi iş parçacığı havuzunda
#: çalıştırır ve varsayılanı 40 iş parçacığıdır. Havuz bundan küçük kalırsa
#: iş parçacıkları bağlantı beklerken sıraya girer, yani olay döngüsünden
#: kurtardığımız eşzamanlılığı havuzda geri kaybederiz. Postgres'in
#: varsayılan `max_connections` değeri 100; tek worker için 40 rahat sığıyor.
POOL_SIZE = 20
MAX_OVERFLOW = 20

#: Bağlantıyı kullanmadan önce yokla. Veritabanı boşta kaldıktan (ya da
#: yeniden başladıktan) sonraki ilk istek bayat bir bağlantıya düşüp
#: `OperationalError` ile ölüyordu: kullanıcı tarafında "bazen hata veriyor,
#: yeniden deneyince geliyor". Yoklamanın bedeli bağlantı başına bir
#: `SELECT 1`.
POOL_RECYCLE_SECONDS = 1800


def engine_options(url: str) -> dict:
    """Bu URL için `create_engine` argümanları.

    SQLite ayrı tutuluyor: bellek içi SQLite `SingletonThreadPool` kullanır ve
    `pool_size`/`max_overflow` KABUL ETMEZ -- testler `DATABASE_URL`'i
    `sqlite+pysqlite:///:memory:` yaptığı için (bkz. `tests/conftest.py`) bu
    argümanları koşulsuz vermek import anında `TypeError` atardı.
    """
    if url.startswith("sqlite"):
        return {}
    return {
        "pool_size": POOL_SIZE,
        "max_overflow": MAX_OVERFLOW,
        "pool_pre_ping": True,
        "pool_recycle": POOL_RECYCLE_SECONDS,
    }


engine = create_engine(settings.DATABASE_URL, **engine_options(settings.DATABASE_URL))
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
