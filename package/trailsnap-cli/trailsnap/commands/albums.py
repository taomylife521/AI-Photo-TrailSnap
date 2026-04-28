from utils import make_request, load_env
from output import output, output_error, set_formatter, OutputFormatter

def setup_parser(subparsers):
    parser = subparsers.add_parser("albums", help="管理和查询相册")
    sub_subparsers = parser.add_subparsers(dest="subcommand", help="可用操作")
    sub_subparsers.required = True

    list_parser = sub_subparsers.add_parser("list", help="查询相册列表")
    list_parser.add_argument("--skip", type=int, default=0, help="跳过 N 张相册")
    list_parser.add_argument("--limit", type=int, default=100, help="限制返回 N 张相册")
    list_parser.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    list_parser.set_defaults(func=execute_list)

def execute_list(args):
    set_formatter(args.format)
    data = make_request("/albums", {"skip": args.skip, "limit": args.limit})
    if data:
        albums = [{
            "id": album["id"],
            "name": album["name"],
            "count": album["num_photos"],
            "description": album["description"],
            "condition": album["condition"],
            "type": album["type"]
        } for album in data]
        output(albums)
    else:
        output_error("未查询到相册记录")
