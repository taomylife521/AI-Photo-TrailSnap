import request from '@/utils/request';
import type { Photo } from '@/types/album';

export interface TagStats {
  id: string
  tag_name: string
  count: number
  cover: Photo | null
}

export const classificationService = {
  async getTags(skip: number = 0, limit: number = 100) {
    const data = await request.get<TagStats[]>('/api/tags', {
      params: { skip, limit }
    });
    return data.data;
  },
  
  async getTagPhotos(name: string, skip: number = 0, limit: number = 50) {
    const data = await request.get<Photo[]>(`/api/tags/${encodeURIComponent(name)}/photos`, {
      params: { skip, limit }
    });
    return data.data;
  },

  async removePhotosFromTag(tagName: string, photoIds: string[]) {
    const data = await request.post(`/api/tags/${encodeURIComponent(tagName)}/remove-photos`, {
      photo_ids: photoIds
    });
    return data.data;
  },

  async deleteTag(tagName: string) {
      await request.delete(`/api/tags/${tagName}`);
  },

  async renameTag(oldName: string, newName: string) {
      const data = await request.put(`/api/tags/${oldName}`, { new_name: newName });
      return data.data;
  },

  async mergeTags(targetName: string, sourceNames: string[]) {
      const data = await request.post('/api/tags/merge', {
          target_name: targetName,
          source_names: sourceNames
      });
      return data.data;
  }
};
