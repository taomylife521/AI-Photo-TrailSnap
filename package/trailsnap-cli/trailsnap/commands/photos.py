from utils import make_request, load_env
from output import output, output_success, output_error, set_formatter, OutputFormatter

def setup_parser(subparsers):
    parser = subparsers.add_parser("photos", help="管理和查询照片")
    sub_subparsers = parser.add_subparsers(dest="subcommand", help="可用操作")
    sub_subparsers.required = True

    # list subcommand
    list_parser = sub_subparsers.add_parser("list", help="查询照片列表")
    list_parser.add_argument("--skip", type=int, default=0, help="跳过 N 张照片")
    list_parser.add_argument("--limit", type=int, default=10, help="限制返回 N 张照片")
    list_parser.add_argument("--order_by", type=str, default="memory_score", help="排序字段，默认按值得回忆评分排序，可选值：quality_score,memory_score,photo_time")
    list_parser.add_argument("--image-type", help="按图片类型过滤照片，多个类型用逗号分隔，可选值：Camera,Screenshot,Other")
    # start_time 过滤照片
    list_parser.add_argument("--start-time", help="按开始时间过滤照片，格式为 YYYY-MM-DD HH:MM:SS")
    # end_time 过滤照片
    list_parser.add_argument("--end-time", help="按结束时间过滤照片，格式为 YYYY-MM-DD HH:MM:SS")
    list_parser.add_argument("--album-id", help="按相册 ID 过滤，多个 ID 用逗号分隔")
    list_parser.add_argument("--people-id", help="按人物 ID 过滤，多个 ID 用逗号分隔")
    list_parser.add_argument("--tag-id", help="按标签 ID 过滤，多个 ID 用逗号分隔")
    list_parser.add_argument("--city", help="按城市过滤，多个城市用逗号分隔")
    list_parser.add_argument("--province", help="按省份过滤，多个省份用逗号分隔")
    list_parser.add_argument("--scene", help="按景区过滤，多个景区用逗号分隔")
    list_parser.add_argument("--make", help="按相机品牌过滤，多个品牌用逗号分隔")
    list_parser.add_argument("--model", help="按相机型号过滤，多个型号用逗号分隔")
    list_parser.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    list_parser.set_defaults(func=execute_list)

    # info subcommand
    info_parser = sub_subparsers.add_parser("info", help="获取单张照片信息")
    info_parser.add_argument("--photo-id", required=True, help="照片ID")
    info_parser.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    info_parser.set_defaults(func=execute_info)

    # delete subcommand
    delete_parser = sub_subparsers.add_parser("delete", help="删除照片")
    delete_parser.add_argument("--photo-id", required=True, help="照片ID")
    delete_parser.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    delete_parser.set_defaults(func=execute_delete)

def execute_list(args):
    set_formatter(args.format)
    params = {
        "skip": args.skip,
        "limit": args.limit,
        "start_time": args.start_time,
        "end_time": args.end_time,
        "image_types": args.image_type.split(",") if args.image_type else [],
        "scenes": args.scene.split(",") if args.scene else [],
        "album_ids": args.album_id.split(",") if args.album_id else [],
        "cities": args.city.split(",") if args.city else [],
        "provinces": args.province.split(",") if args.province else [],
        "makes": args.make.split(",") if args.make else [],
        "models": args.model.split(",") if args.model else [],
        "face_ids": args.people_id.split(",") if args.people_id else [],
        "tag_ids": args.tag_id.split(",") if args.tag_id else [],
        "order_by": args.order_by
    }
    data = make_request("/photos/detail", params)
    env = load_env()
    base_url = env.get("TRAILSNAP_API_URL", "")

    if data:
        photos = []
        for photo in data:
            metadata = photo.get("metadata_info", {})
            if not metadata:
                metadata = {}
            image_description = photo.get("image_description", {})
            if not image_description:
                image_description = {}
            photos.append({
                "id": photo["id"],
                "url": f"{base_url}/medias/{photo['id']}/file",
                "filename": photo["filename"],
                "file_type": photo["file_type"],
                "photo_time": photo["photo_time"],
                "address": metadata.get("address", ""),
                "description": {
                    "description": image_description.get("description", ""),
                    "tags": image_description.get("tags", []),
                    "memory_score": image_description.get("memory_score", 0),
                    "quality_score": image_description.get("quality_score", 0),
                    "narrative": image_description.get("narrative", "")
                }
            })
        output(photos)
    else:
        output_error("没有查询到照片列表")

def execute_info(args):
    set_formatter(args.format)
    data = make_request(f"/photos/{args.photo_id}/metadata")
    description_data = make_request(f"/photos/{args.photo_id}/description")
    if not description_data:
        description_data = {}
    if data:
        info = {
            # "file_path": data["file_path"],
            "address": data["address"],
            "albums": data["albums"],
            "tags": data["tags"],
            "faces_identities": data["faces_identities"],
            "description": description_data
        }
        output(info)
    else:
        output_error("未查询到照片信息")

def execute_delete(args):
    set_formatter(args.format)
    data = make_request(f"/photos/{args.photo_id}", method="DELETE")
    if data:
        output_success(f"照片 {args.photo_id} 删除成功")
    else:
        output_error("照片删除失败或不存在")
