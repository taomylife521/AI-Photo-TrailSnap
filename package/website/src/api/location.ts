import request from '@/utils/request';
import type { Location, Scene, SceneCreate, SceneUpdate, LocationStatistics, TimelineResponse } from '@/types/location';
import type { Photo } from '@/types/album';

export const locationService = {
  async getYears() {
    const data = await request.get<number[]>('/api/locations/years');
    return data.data;
  },

  async searchLocations(q: string) {
    const data = await request.get<{ label: string, value: { province?: string, city?: string, district?: string } }[]>('/api/locations/search', {
      params: { q }
    });
    return data.data;
  },

  async getLocations(level: 'city' | 'province' | 'district' | 'scene' = 'city', skip: number = 0, limit: number = 100, year?: number | null) {
    const data = await request.get<Location[]>('/api/locations', {
      params: { level, skip, limit, year: year || undefined }
    });
    return data.data;
  },

  async getStatistics() {
    const data = await request.get<LocationStatistics>('/api/locations/statistics');
    return data.data;
  },

  async getDistribution(level: 'city' | 'province' | 'district' | 'scene' = 'city', year?: number | null) {
    const data = await request.get<{name: string, count: number, level: string}[]>('/api/locations/distribution', {
      params: { level, year: year || undefined }
    });
    return data.data;
  },
  
  async getLocationPhotos(name: string, level: 'city' | 'province' | 'district' | 'scene' = 'city', skip: number = 0, limit: number = 50, year?: number | null) {
    const data = await request.get<Photo[]>(`/api/locations/${name}/photos`, {
      params: { level, skip, limit, year: year || undefined }
    });
    return data.data;
  },

  async getTimelineNodes(skip: number = 0, limit: number = 100, year?: number | null) {
    const data = await request.get<TimelineResponse>('/api/locations/timeline', {
      params: { skip, limit, year: year || undefined }
    });
    return data.data;
  },

  async getMapMarkers(year?: number | null) {
    const data = await request.get<{id: string, lat: number, lng: number}[]>('/api/locations/markers', {
      params: { year: year || undefined }
    });
    return data.data;
  },

  async getScene(id: string) {
    const data = await request.get<Scene>(`/api/locations/scenes/${id}`);
    return data.data;
  },

  async createScene(scene: SceneCreate) {
    const data = await request.post<Scene>('/api/locations/scenes', scene);
    return data.data;
  },

  async updateScene(id: string, scene: SceneUpdate) {
    const data = await request.put<Scene>(`/api/locations/scenes/${id}`, scene);
    return data.data;
  },

  async getScenesList(skip: number = 0, limit: number = 100, year?: number | null) {
    const data = await request.get<Scene[]>('/api/locations/scenes/list', {
      params: { skip, limit, year: year || undefined }
    });
    return data.data;
  },

  async deleteScene(id: string) {
    const data = await request.delete(`/api/locations/scenes/${id}`);
    return data.data;
  }
};
