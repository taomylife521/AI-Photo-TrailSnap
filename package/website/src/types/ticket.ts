// src/types/ticket.ts

// 后端原始数据接口 (Snake Case)
export interface TicketBackend {
  id: number | string; // 兼容 UUID
  train_code: string;
  departure_station: string;
  arrival_station: string;
  date_time: string; // "YYYY-MM-DD HH:mm:ss"
  carriage: string;
  seat_num: string;
  berth_type?: string;
  price: number;
  seat_type: string;
  name: string;
  discount_type?: string;
  total_running_time: number; // minutes
  total_mileage: number; // km
  stop_stations?: string;
  comments?: string;
  photo_id?: string;
  type?: 'train'; // 标识字段
}

export interface FlightTicketBackend {
  id: string;
  flight_code: string;
  departure_city: string;
  arrival_city: string;
  date_time: string;
  price: number;
  name: string;
  total_running_time: number;
  total_mileage: number;
  comments?: string;
  photo_id?: string;
  type?: 'flight'; // 标识字段
}

export type UniversalTicket = TicketBackend | FlightTicketBackend;

// 前端展示用的数据接口 (Camel Case)
export interface TicketFrontend {
  id: string;
  type: 'train' | 'flight'; // 新增类型标识
  from: string;
  to: string;
  trainCode: string; // 对于飞机票，这里存航班号
  name: string;
  date: string;       // "YYYY-MM-DD"
  time: string;       // "HH:mm"
  dateTime: string;   // 原始完整时间字符串
  carriage?: string;  // 可选
  seatNumber?: string; // 可选
  berthType?: string; // 可选
  price: number;
  seatType?: string; // 可选
  discountType?: string; // 可选
  totalRunningTime: number;
  distance: number;
  comments: string;
  duration: string; // "xh yymin"
  photo_id?: string; // 可选
}

// 表单提交用的数据接口
export interface TicketFormData {
  id?: string | null;
  from: string;
  to: string;
  train_code: string;
  name: string;
  dateTime: string;
  carriage: string;
  seatNumber: string;
  berthType: string;
  price: number;
  seatType: string;
  discountType: string;
  totalRunningTime: number;
  distance: number;
  comments: string;
}

export interface FlightTicketFormData {
  id?: string | null;
  flight_code: string;
  departure_city: string;
  arrival_city: string;
  date_time: string;
  price: number;
  name: string;
  total_running_time: number;
  total_mileage: number;
  comments: string;
}

// 筛选查询参数
export interface TicketQueryParams {
  skip?: number;
  limit?: number;
  train_code?: string;
  flight_code?: string;
  departure_station?: string;
  arrival_station?: string;
  name?: string;
  start_date?: string;
  end_date?: string;
}

export type SortType = 'date' | 'distance' | 'duration' | 'price';
export type FilterType = 'all' | 'highspeed' | 'normal';
