#!/usr/bin/env python3
"""Read HashLink bytecode metadata without executing the bytecode."""

from __future__ import annotations

import argparse
import json
import re
import struct
from pathlib import Path


KIND_NAMES = {
    0: "void",
    1: "u8",
    2: "u16",
    3: "i32",
    4: "i64",
    5: "f32",
    6: "f64",
    7: "bool",
    8: "bytes",
    9: "dynamic",
    10: "function",
    11: "object",
    12: "array",
    13: "type",
    14: "ref",
    15: "virtual",
    16: "dynamic_object",
    17: "abstract",
    18: "enum",
    19: "nullable",
    20: "method",
    21: "struct",
    22: "packed",
    23: "guid",
}

OPCODES = [
    ("OMov", 2), ("OInt", 2), ("OFloat", 2), ("OBool", 2),
    ("OBytes", 2), ("OString", 2), ("ONull", 1), ("OAdd", 3),
    ("OSub", 3), ("OMul", 3), ("OSDiv", 3), ("OUDiv", 3),
    ("OSMod", 3), ("OUMod", 3), ("OShl", 3), ("OSShr", 3),
    ("OUShr", 3), ("OAnd", 3), ("OOr", 3), ("OXor", 3),
    ("ONeg", 2), ("ONot", 2), ("OIncr", 1), ("ODecr", 1),
    ("OCall0", 2), ("OCall1", 3), ("OCall2", 4), ("OCall3", 5),
    ("OCall4", 6), ("OCallN", -1), ("OCallMethod", -1),
    ("OCallThis", -1), ("OCallClosure", -1), ("OStaticClosure", 2),
    ("OInstanceClosure", 3), ("OVirtualClosure", 3), ("OGetGlobal", 2),
    ("OSetGlobal", 2), ("OField", 3), ("OSetField", 3),
    ("OGetThis", 2), ("OSetThis", 2), ("ODynGet", 3), ("ODynSet", 3),
    ("OJTrue", 2), ("OJFalse", 2), ("OJNull", 2), ("OJNotNull", 2),
    ("OJSLt", 3), ("OJSGte", 3), ("OJSGt", 3), ("OJSLte", 3),
    ("OJULt", 3), ("OJUGte", 3), ("OJNotLt", 3), ("OJNotGte", 3),
    ("OJEq", 3), ("OJNotEq", 3), ("OJAlways", 1), ("OToDyn", 2),
    ("OToSFloat", 2), ("OToUFloat", 2), ("OToInt", 2),
    ("OSafeCast", 2), ("OUnsafeCast", 2), ("OToVirtual", 2),
    ("OLabel", 0), ("ORet", 1), ("OThrow", 1), ("ORethrow", 1),
    ("OSwitch", -1), ("ONullCheck", 1), ("OTrap", 2), ("OEndTrap", 1),
    ("OGetI8", 3), ("OGetI16", 3), ("OGetMem", 3), ("OGetArray", 3),
    ("OSetI8", 3), ("OSetI16", 3), ("OSetMem", 3), ("OSetArray", 3),
    ("ONew", 1), ("OArraySize", 2), ("OType", 2), ("OGetType", 2),
    ("OGetTID", 2), ("ORef", 2), ("OUnref", 2), ("OSetref", 2),
    ("OMakeEnum", -1), ("OEnumAlloc", 2), ("OEnumIndex", 2),
    ("OEnumField", 4), ("OSetEnumField", 3), ("OAssert", 0),
    ("ORefData", 2), ("ORefOffset", 3), ("ONop", 0),
    ("OPrefetch", 3), ("OAsm", 3), ("OCatch", 1), ("OLast", 0),
]


class Reader:
    def __init__(self, data: bytes):
        self.data = data
        self.position = 0

    def take(self, size: int) -> bytes:
        end = self.position + size
        if size < 0 or end > len(self.data):
            raise ValueError(f"unexpected end of bytecode at 0x{self.position:x}")
        value = self.data[self.position : end]
        self.position = end
        return value

    def byte(self) -> int:
        return self.take(1)[0]

    def i32(self) -> int:
        return struct.unpack("<i", self.take(4))[0]

    def index(self) -> int:
        first = self.byte()
        if first & 0x80 == 0:
            return first & 0x7F
        if first & 0x40 == 0:
            value = self.byte() | ((first & 31) << 8)
            return value if first & 0x20 == 0 else -value
        value = (
            ((first & 31) << 24)
            | (self.byte() << 16)
            | (self.byte() << 8)
            | self.byte()
        )
        return value if first & 0x20 == 0 else -value

    def uindex(self) -> int:
        value = self.index()
        if value < 0:
            raise ValueError(f"negative unsigned index at 0x{self.position:x}")
        return value


def read_strings(reader: Reader, count: int) -> list[str]:
    blob_size = reader.i32()
    blob = reader.take(blob_size)
    lengths = [reader.uindex() for _ in range(count)]
    strings: list[str] = []
    offset = 0
    for length in lengths:
        end = offset + length
        if end >= len(blob) or blob[end] != 0:
            raise ValueError("invalid HashLink string table")
        strings.append(blob[offset:end].decode("utf-8", errors="replace"))
        offset = end + 1
    return strings


def parse_type(reader: Reader, strings: list[str], index: int) -> dict[str, object]:
    kind = reader.byte()
    result: dict[str, object] = {
        "index": index,
        "kind": KIND_NAMES.get(kind, f"unknown_{kind}"),
    }

    if kind in (10, 20):
        argument_count = reader.byte()
        result["arguments"] = [reader.index() for _ in range(argument_count)]
        result["returns"] = reader.index()
    elif kind in (11, 21):
        name_index = reader.index()
        result["name"] = strings[name_index]
        result["super"] = reader.index()
        result["global"] = reader.uindex()
        field_count = reader.uindex()
        prototype_count = reader.uindex()
        binding_count = reader.uindex()
        result["fields"] = [
            {"name": strings[reader.index()], "type_index": reader.index()}
            for _ in range(field_count)
        ]
        result["prototypes"] = [
            {
                "name": strings[reader.index()],
                "function_index": reader.uindex(),
                "prototype_index": reader.index(),
            }
            for _ in range(prototype_count)
        ]
        result["bindings"] = [
            {"field_index": reader.uindex(), "function_index": reader.uindex()}
            for _ in range(binding_count)
        ]
    elif kind == 15:
        result["fields"] = [
            {"name": strings[reader.index()], "type_index": reader.index()}
            for _ in range(reader.uindex())
        ]
    elif kind == 17:
        result["name"] = strings[reader.index()]
    elif kind == 18:
        result["name"] = strings[reader.index()]
        result["global"] = reader.uindex()
        constructs = []
        for _ in range(reader.uindex()):
            construct = {"name": strings[reader.index()]}
            construct["parameters"] = [reader.index() for _ in range(reader.uindex())]
            constructs.append(construct)
        result["constructs"] = constructs
    elif kind in (14, 19, 22):
        result["parameter_type"] = reader.index()
    elif kind not in KIND_NAMES:
        raise ValueError(f"unknown HashLink type kind {kind} at type {index}")

    return result


def parse_opcode(reader: Reader) -> dict[str, object]:
    opcode_index = reader.byte()
    if opcode_index >= len(OPCODES) - 1:
        raise ValueError(f"invalid HashLink opcode {opcode_index}")
    name, argument_count = OPCODES[opcode_index]
    if argument_count >= 0:
        arguments = [reader.index() for _ in range(argument_count)]
    elif name == "OSwitch":
        register = reader.uindex()
        case_count = reader.uindex()
        arguments = [register, *[reader.uindex() for _ in range(case_count)], reader.uindex()]
    else:
        first = reader.index()
        second = reader.index()
        extra_count = reader.byte()
        arguments = [first, second, *[reader.index() for _ in range(extra_count)]]
    return {"opcode": name, "arguments": arguments}


def skip_debug_info(reader: Reader, operation_count: int) -> None:
    operation = 0
    while operation < operation_count:
        value = reader.byte()
        if value & 1:
            reader.byte()
        elif value & 2:
            operation += (value >> 2) & 15
        elif value & 4:
            operation += 1
        else:
            reader.take(2)
            operation += 1


def inspect(
    path: Path,
    pattern: re.Pattern[str],
    function_indexes: set[int] | None = None,
    type_indexes: set[int] | None = None,
) -> dict[str, object]:
    data = path.read_bytes()
    reader = Reader(data)
    if reader.take(3) != b"HLB":
        raise ValueError("not a HashLink bytecode file")

    version = reader.byte()
    if version < 2 or version > 5:
        raise ValueError(f"unsupported HashLink bytecode version {version}")

    flags = reader.uindex()
    counts = {
        "integers": reader.uindex(),
        "floats": reader.uindex(),
        "strings": reader.uindex(),
    }
    if version >= 5:
        counts["byte_blobs"] = reader.uindex()
    counts.update(
        {
            "types": reader.uindex(),
            "globals": reader.uindex(),
            "natives": reader.uindex(),
            "functions": reader.uindex(),
            "constants": reader.uindex() if version >= 4 else 0,
            "entrypoint": reader.uindex(),
        }
    )

    integers = [reader.i32() for _ in range(counts["integers"])]
    reader.take(counts["floats"] * 8)
    strings = read_strings(reader, counts["strings"])
    if version >= 5:
        reader.take(reader.i32())
        for _ in range(counts["byte_blobs"]):
            reader.uindex()
    if flags & 1:
        read_strings(reader, reader.uindex())

    types = [parse_type(reader, strings, index) for index in range(counts["types"])]
    global_types = [reader.index() for _ in range(counts["globals"])]
    for _ in range(counts["natives"]):
        reader.index()
        reader.index()
        reader.index()
        reader.uindex()

    selected_functions = []
    wanted_functions = function_indexes or set()
    for _ in range(counts["functions"]):
        function_type = reader.index()
        function_index = reader.uindex()
        register_count = reader.uindex()
        operation_count = reader.uindex()
        registers = [reader.index() for _ in range(register_count)]
        operations = [parse_opcode(reader) for _ in range(operation_count)]
        if function_index in wanted_functions:
            selected_functions.append(
                {
                    "function_index": function_index,
                    "type_index": function_type,
                    "registers": registers,
                    "operations": operations,
                }
            )
        if flags & 1:
            skip_debug_info(reader, operation_count)
            if version >= 3:
                for _ in range(reader.uindex()):
                    reader.uindex()
                    reader.index()
    matches = []
    for type_info in types:
        searchable = [str(type_info.get("name", ""))]
        searchable.extend(
            str(field["name"]) for field in type_info.get("fields", [])
        )
        searchable.extend(
            str(prototype["name"]) for prototype in type_info.get("prototypes", [])
        )
        if type_info["index"] in (type_indexes or set()) or any(
            pattern.search(value) for value in searchable
        ):
            matches.append(type_info)

    return {
        "path": str(path),
        "file_size": len(data),
        "bytecode_version": version,
        "has_debug_data": bool(flags & 1),
        "counts": counts,
        "integers": integers if function_indexes else [],
        "matched_type_count": len(matches),
        "matched_types": matches,
        "selected_functions": selected_functions,
        "global_types": global_types if function_indexes else [],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument(
        "--match",
        default=r"hero|health|shield|combat|target|position|party",
        help="case-insensitive regular expression applied to type and field names",
    )
    parser.add_argument(
        "--function-index",
        action="append",
        type=int,
        default=[],
        help="decode a function with this HashLink function index",
    )
    parser.add_argument(
        "--type-index",
        action="append",
        type=int,
        default=[],
        help="include a HashLink type by its exact index",
    )
    arguments = parser.parse_args()
    report = inspect(
        arguments.path,
        re.compile(arguments.match, re.IGNORECASE),
        set(arguments.function_index),
        set(arguments.type_index),
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
