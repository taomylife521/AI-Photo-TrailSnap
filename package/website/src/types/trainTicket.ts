/**
 * src/types/trainTicket.ts
 * 火车票相关 TS 类型定义（对齐后端 Pydantic 模型）
 */

// 基础类型：铺位类型枚举（限定可选值）
export type BerthType = '上' | '中' | '下' | '无';
// 基础类型：优惠类型枚举
export type DiscountType = '学生票' | '儿童票' | '优惠票' | '全价票';
// 基础类型：座位类型枚举
export type SeatType = '一等座' | '二等座' | '商务座' | '硬座' | '软座' | '硬卧' | '软卧' | '无座' | '一等卧' | '二等卧' | '动卧' | string;

/** 火车票基础类型（创建/响应共用字段） */
export interface TrainTicketBase {
  train_code: string; // 车次号（如G1920）
  departure_station: string; // 出发站
  arrival_station: string; // 到达站
  date_time: string; // 发车时间（格式：YYYY-MM-DD HH:MM:SS，后端 datetime 转前端字符串）
  carriage: string; // 车厢号（如8A、12）
  seat_num: string; // 座位号（如12F、05下）
  berth_type: BerthType; // 铺位类型（默认"无"）
  price: number; // 票价（后端 Decimal 转前端 number）
  seat_type: SeatType; // 座位类型
  name: string; // 乘车人姓名
  discount_type: DiscountType; // 优惠类型（默认"全价票"）
  total_running_time?: number; // 总运行时间（分钟，可选，默认0）
  total_mileage?: number; // 总里程（公里，可选，默认0）
  stop_stations?: string; // 途经站点列表（可选）
  comments?: string; // 备注信息（可选）
}

/** 创建火车票请求类型（和基础类型一致，无额外字段） */
export interface TrainTicketCreate extends TrainTicketBase {}

/** 更新火车票请求类型（所有字段可选） */
export interface TrainTicketUpdate {
  train_code?: string;
  departure_station?: string;
  arrival_station?: string;
  date_time?: string;
  carriage?: string;
  seat_num?: string;
  berth_type?: BerthType;
  price?: number;
  seat_type?: SeatType;
  name?: string;
  discount_type?: DiscountType;
  total_running_time?: number;
  total_mileage?: number;
  stop_stations?: string;
  comments?: string;
}

/** 火车票响应类型（包含数据库额外字段） */
export interface TrainTicketResponse extends TrainTicketBase {
  id: number; // 数据库主键ID
  created_at: string; // 创建时间（格式：YYYY-MM-DD HH:MM:SS）
  updated_at: string; // 更新时间（格式：YYYY-MM-DD HH:MM:SS）
}

/** 火车票列表响应类型（分页） */
export interface TrainTicketListResponse {
  total: number; // 总记录数
  items: TrainTicketResponse[]; // 火车票列表数据
}

/** 获取火车票列表的查询参数类型 */
export interface TrainTicketQueryParams {
  skip?: number; // 跳过的记录数（默认0）
  limit?: number; // 每页最大记录数（默认10，最大100）
  train_code?: string; // 按车次号模糊查询
  name?: string; // 按乘车人姓名模糊查询
  departure_station?: string; // 按出发站模糊查询
  arrival_station?: string; // 按到达站模糊查询
  start_date?: string; // 发车时间起始（格式：YYYY-MM-DD）
  end_date?: string; // 发车时间结束（格式：YYYY-MM-DD）
}