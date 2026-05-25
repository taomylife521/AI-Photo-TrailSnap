import request from '@/utils/request';
import type { Task as TaskResponse } from './tasks';
import type { Photo } from '@/types/album';

export interface DuplicatePhotoGroup {
  md5: string;
  photos: Photo[];
}

export const toolboxApi = {
  // Trigger duplicate photo scan task
  async scanDuplicatePhotos() {
    const data = await request.post<TaskResponse>('/api/toolbox/duplicate-photos/scan');
    return data.data;
  },

  // Get grouped duplicate photos
  async getDuplicatePhotos() {
    const data = await request.get<DuplicatePhotoGroup[]>('/api/toolbox/duplicate-photos')
    return data.data
  },

  async createOrganizeTask(payload: { target_root_path: string, strategy: string, action: string, time_granularity?: string, time_format?: string, location_granularity?: string, location_format?: string }) {
    const data = await request.post<TaskResponse>('/api/toolbox/organize/tasks', payload)
    return data.data
  },

  async getLatestOrganizeTask() {
    const data = await request.get<TaskResponse | null>('/api/toolbox/organize/tasks/latest')
    return data.data
  }
};
