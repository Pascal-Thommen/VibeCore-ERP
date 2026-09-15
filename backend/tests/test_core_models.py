from app.db.base import Base, CORE_SCHEMA
from app.models import Account, Document, DocumentItem, Partner, Product, Tax


def test_core_models_register_the_required_tables_with_jsonb_metadata() -> None:
    models = (Partner, Account, Tax, Product, Document, DocumentItem)

    assert {model.__table__.name for model in models} == {
        "partner",
        "account",
        "tax",
        "product",
        "document",
        "document_item",
    }

    for model in models:
        table = model.__table__
        assert table.schema == CORE_SCHEMA
        assert table.name in {table.name for table in Base.metadata.tables.values()}
        assert table.c.metadata.type.__class__.__name__ == "JSONB"


def test_document_models_preserve_sifen_and_exact_financial_fields() -> None:
    document = Document.__table__
    item = DocumentItem.__table__

    assert document.c.sifen_cdc.type.length == 44
    assert document.c.timbrado_number.type.length == 8
    assert document.c.establishment_code.type.length == 3
    assert document.c.point_of_issue_code.type.length == 3
    assert document.c.sifen_document_number.type.length == 7
    assert document.c.exchange_rate.type.precision == 24
    assert document.c.exchange_rate.type.scale == 12
    assert item.c.quantity.type.precision == 20
    assert item.c.quantity.type.scale == 6
    assert item.c.unit_price.type.precision == 20
    assert item.c.unit_price.type.scale == 6

    foreign_keys = {
        foreign_key.parent.name: foreign_key.ondelete for foreign_key in item.foreign_keys
    }
    assert foreign_keys == {
        "document_id": "CASCADE",
        "product_id": "RESTRICT",
        "tax_id": "RESTRICT",
    }
