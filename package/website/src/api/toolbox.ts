import request from '@/utils/request';
import type { TaskResponse } from './photo';
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
    const data = await request.get<DuplicatePhotoGroup[]>('/api/toolbox/duplicate-photos');
    return data.data;
  }
};
