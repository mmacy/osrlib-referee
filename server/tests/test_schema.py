from osrlib.crawl.commands import ALL_COMMAND_CLASSES, AnyCommand
from pydantic import TypeAdapter


def test_deps_resolve_and_union_schema_generates():
    schema = TypeAdapter(AnyCommand).json_schema()

    assert schema["discriminator"]["propertyName"] == "command_type"
    assert len(schema["oneOf"]) == len(ALL_COMMAND_CLASSES)
