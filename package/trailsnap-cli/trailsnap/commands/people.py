from utils import make_request
from output import output, output_error, set_formatter, OutputFormatter

def setup_parser(subparsers):
    parser = subparsers.add_parser("people", help="管理和查询人物（面部识别）")
    sub_subparsers = parser.add_subparsers(dest="subcommand", help="可用操作")
    sub_subparsers.required = True

    list_parser = sub_subparsers.add_parser("list", help="查询人物列表")
    list_parser.add_argument("--limit", type=int, default=100, help="返回的记录数，默认 100")
    list_parser.add_argument("--types", type=str, default="named", help="查询类型，默认 named, 可选值：named,unnamed,hidden 中的一个或多个,逗号分隔")
    list_parser.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    list_parser.set_defaults(func=execute_list)

def execute_list(args):
    set_formatter(args.format)
    valid_types = {"named", "unnamed", "hidden"}
    if not set(args.types.split(",")) <= valid_types:
        output_error("types参数值必须为 named,unnamed,hidden 中的一个或多个")
        return

    args.types = args.types.split(",")
    data = make_request("/faces/identities", {"page": 1, "limit": args.limit, "types": args.types})
    if data:
        identities = [{
            "id": identity["id"],
            "name": identity["identity_name"],
            "tags": identity["tags"],
            "description": identity["description"],
            "face_count": identity["face_count"]
        } for identity in data]
        output(identities)
    else:
        output_error("未查询到人物记录")
