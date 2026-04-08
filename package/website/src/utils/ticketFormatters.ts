// src/utils/ticketFormatters.ts
import type { TicketBackend, TicketFrontend, TicketFormData, UniversalTicket, FlightTicketBackend } from '@/types/ticket';

// 格式化时长 (分钟 -> "xh yymin")
export const formatDuration = (minutes: number): string => {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return h > 0 ? `${h}h ${m}min` : `${m}min`;
};

// 后端数据转前端数据
export const formatTicketToFrontend = (ticket: UniversalTicket): TicketFrontend => {
  // 兼容 ISO 时间格式 (T) 和 普通空格分隔
  const normalizedDateTime = ticket.date_time.replace('T', ' ');
  const [datePart, timePart] = normalizedDateTime.split(' ');
  const type = ticket.type || 'train'; // 默认为 train

  if (type === 'flight') {
      const flight = ticket as FlightTicketBackend;
      return {
          id: flight.id,
          type: 'flight',
          from: flight.departure_city,
          to: flight.arrival_city,
          trainCode: flight.flight_code, // 复用 trainCode 字段显示航班号
          name: flight.name || '',
          date: datePart,
          time: timePart || '',
          dateTime: flight.date_time,
          price: flight.price,
          totalRunningTime: flight.total_running_time || 0,
          distance: flight.total_mileage || 0,
          comments: flight.comments || '',
          duration: formatDuration(flight.total_running_time || 0),
          photo_id: flight.photo_id,
          // 飞机票可选字段置空
          carriage: undefined,
          seatNumber: undefined,
          berthType: undefined,
          seatType: undefined,
          discountType: undefined
      };
  } else {
      const train = ticket as TicketBackend;
      return {
          id: train.id,
          type: 'train',
          from: train.departure_station,
          to: train.arrival_station,
          trainCode: train.train_code,
          name: train.name || '',
          date: datePart,
          time: timePart || '',
          dateTime: train.date_time,
          carriage: train.carriage,
          seatNumber: train.seat_num,
          berthType: train.berth_type || '无',
          price: train.price,
          seatType: train.seat_type,
          discountType: train.discount_type || '全价票',
          totalRunningTime: train.total_running_time || 0,
          distance: train.total_mileage || 0,
          comments: train.comments || '',
          duration: formatDuration(train.total_running_time || 0),
          photo_id: train.photo_id,
      };
  }
};

// 前端表单数据转后端数据
export const formatFormToBackend = (formData: TicketFormData): Partial<TicketBackend> => ({
  train_code: formData.train_code,
  departure_station: formData.from,
  arrival_station: formData.to,
  date_time: formData.dateTime,
  carriage: formData.carriage,
  seat_num: formData.seatNumber,
  berth_type: formData.berthType,
  price: formData.price,
  seat_type: formData.seatType,
  name: formData.name,
  discount_type: formData.discountType,
  total_running_time: formData.totalRunningTime || 0,
  total_mileage: formData.distance || 0,
  stop_stations: '',
  comments: formData.comments,
});

// 简单的防抖函数 (泛型)
export function debounce<T extends (...args: any[]) => any>(fn: T, delay: number = 500) {
  let timer: ReturnType<typeof setTimeout> | null = null;
  
  const debounced = (...args: Parameters<T>) => {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };

  debounced.cancel = () => {
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
  };

  return debounced;
}