import axios, { AxiosError, AxiosInstance } from 'axios';
import type {
  LoginRequest,
  LoginResponse,
  User,
  SystemStatus,
  ActiveStreamsResponse,
  StreamsHistoryResponse,
  StreamHistory,
  StreamSummary,
  CurrentBandwidthResponse,
  BandwidthHistoryResponse,
  BandwidthSummary,
  BandwidthChartDataResponse,
  RestoreSpeedsResponse,
  ManualThrottleRequest,
  ManualThrottleResponse,
  MonitoringControlResponse,
  SettingsSectionsResponse,
  SettingsSectionResponse,
  SettingsUpdateResponse,
  TestConnectionResponse,
  ExportYAMLResponse,
  ConfigHistoryResponse,
  DecisionLogsResponse,
  SNMPDiscoverResponse,
  SNMPSpeedResponse,
} from '@/types';

class ApiClient {
  private client: AxiosInstance;
  private tokenKey = 'speedarr_token';
  private activeRequests: Map<string, AbortController> = new Map();
  // Request deduplication: cache in-flight GET requests to prevent duplicate concurrent calls
  private pendingRequests: Map<string, Promise<unknown>> = new Map();

  constructor() {
    this.client = axios.create({
      baseURL: '/api',
      headers: {
        'Content-Type': 'application/json',
      },
      timeout: 30000, // 30 second timeout
    });

    // Add auth token to requests
    this.client.interceptors.request.use((config) => {
      const token = this.getToken();
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
      return config;
    });

    // Handle 401 responses - only redirect to login if user had a token (session expired).
    // Anonymous users browsing the public dashboard should not be redirected.
    this.client.interceptors.response.use(
      (response) => response,
      (error: AxiosError) => {
        const isAuthRequest = error.config?.url?.includes('/auth/login') ||
                              error.config?.url?.includes('/auth/me') ||
                              error.config?.url?.includes('/auth/first-run');
        if (error.response?.status === 401 && !isAuthRequest && this.getToken()) {
          this.clearToken();
          window.location.href = '/login';
        }
        return Promise.reject(error);
      }
    );
  }

  // Token management
  getToken(): string | null {
    return localStorage.getItem(this.tokenKey);
  }

  setToken(token: string): void {
    localStorage.setItem(this.tokenKey, token);
  }

  clearToken(): void {
    localStorage.removeItem(this.tokenKey);
  }

  isAuthenticated(): boolean {
    return !!this.getToken();
  }

  // AbortController management for request cancellation
  createAbortController(requestId: string): AbortController {
    // Cancel any existing request with the same ID
    this.cancelRequest(requestId);
    const controller = new AbortController();
    this.activeRequests.set(requestId, controller);
    return controller;
  }

  cancelRequest(requestId: string): void {
    const controller = this.activeRequests.get(requestId);
    if (controller) {
      controller.abort();
      this.activeRequests.delete(requestId);
    }
  }

  cancelAllRequests(): void {
    this.activeRequests.forEach((controller) => controller.abort());
    this.activeRequests.clear();
  }

  cleanupRequest(requestId: string): void {
    this.activeRequests.delete(requestId);
  }

  /**
   * Deduplicated GET request - if an identical request is already in-flight,
   * returns the same promise instead of making a duplicate request.
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  private async deduplicatedGet<T>(url: string, params?: any): Promise<T> {
    // Create a cache key from URL and params
    const cacheKey = params ? `${url}?${JSON.stringify(params)}` : url;

    // Check if request is already in-flight
    const pending = this.pendingRequests.get(cacheKey);
    if (pending) {
      return pending as Promise<T>;
    }

    // Make the request and cache the promise
    const requestPromise = this.client.get<T>(url, { params })
      .then(response => response.data)
      .finally(() => {
        // Clean up after request completes (success or error)
        this.pendingRequests.delete(cacheKey);
      });

    this.pendingRequests.set(cacheKey, requestPromise);
    return requestPromise;
  }

  // Authentication endpoints
  async checkFirstRun(): Promise<{ first_run: boolean; user_count: number }> {
    const response = await this.client.get('/auth/first-run');
    return response.data;
  }

  async register(username: string, password: string): Promise<{
    success: boolean;
    message: string;
    access_token: string;
    token_type: string;
    user: { id: number; username: string; role: string };
  }> {
    const response = await this.client.post('/auth/register', { username, password });
    this.setToken(response.data.access_token);
    return response.data;
  }

  async login(credentials: LoginRequest): Promise<LoginResponse> {
    const response = await this.client.post<LoginResponse>('/auth/login', credentials);
    this.setToken(response.data.access_token);
    return response.data;
  }

  async logout(): Promise<void> {
    this.clearToken();
  }

  async getCurrentUser(): Promise<User> {
    const response = await this.client.get<User>('/auth/me');
    return response.data;
  }

  async changePassword(currentPassword: string, newPassword: string): Promise<void> {
    await this.client.post('/auth/change-password', {
      current_password: currentPassword,
      new_password: newPassword,
    });
  }

  async getDecisionLogs(params: { days: number; limit: number; offset: number; changes_only?: boolean }): Promise<DecisionLogsResponse> {
    const response = await this.client.get<DecisionLogsResponse>('/decisions/logs', { params });
    return response.data;
  }

  // Status endpoints
  async getSystemStatus(): Promise<SystemStatus> {
    return this.deduplicatedGet<SystemStatus>('/status/current');
  }

  async getHealth(): Promise<{ status: string; version: string }> {
    const response = await this.client.get('/status/health');
    return response.data;
  }

  // Stream endpoints
  async getActiveStreams(): Promise<ActiveStreamsResponse> {
    return this.deduplicatedGet<ActiveStreamsResponse>('/streams/active');
  }

  async getStreamHistory(params?: {
    days?: number;
    user?: string;
    limit?: number;
    offset?: number;
  }): Promise<StreamsHistoryResponse> {
    const response = await this.client.get<StreamsHistoryResponse>('/streams/history', {
      params,
    });
    return response.data;
  }

  async getStreamDetails(streamId: number): Promise<StreamHistory> {
    const response = await this.client.get<StreamHistory>(`/streams/history/${streamId}`);
    return response.data;
  }

  async getStreamSummary(days?: number): Promise<StreamSummary> {
    const response = await this.client.get<StreamSummary>('/streams/summary', {
      params: days ? { days } : undefined
    });
    return response.data;
  }

  // Bandwidth endpoints
  async getCurrentBandwidth(): Promise<CurrentBandwidthResponse> {
    const response = await this.client.get<CurrentBandwidthResponse>('/bandwidth/current');
    return response.data;
  }

  async getBandwidthHistory(params?: {
    hours?: number;
    limit?: number;
  }): Promise<BandwidthHistoryResponse> {
    const response = await this.client.get<BandwidthHistoryResponse>('/bandwidth/history', {
      params,
    });
    return response.data;
  }

  async getBandwidthSummary(): Promise<BandwidthSummary> {
    const response = await this.client.get<BandwidthSummary>('/bandwidth/summary');
    return response.data;
  }

  async getBandwidthChartData(params?: {
    hours?: number;
    interval_minutes?: number;
  }): Promise<BandwidthChartDataResponse> {
    return this.deduplicatedGet<BandwidthChartDataResponse>('/bandwidth/chart-data', params);
  }

  // Control endpoints
  async restoreSpeeds(): Promise<RestoreSpeedsResponse> {
    const response = await this.client.post<RestoreSpeedsResponse>('/control/restore');
    return response.data;
  }

  async manualThrottle(limits: ManualThrottleRequest): Promise<ManualThrottleResponse> {
    const response = await this.client.post<ManualThrottleResponse>('/control/throttle', limits);
    return response.data;
  }

  async pauseMonitoring(): Promise<MonitoringControlResponse> {
    const response = await this.client.post<MonitoringControlResponse>('/control/pause');
    return response.data;
  }

  async resumeMonitoring(): Promise<MonitoringControlResponse> {
    const response = await this.client.post<MonitoringControlResponse>('/control/resume');
    return response.data;
  }

  // Settings endpoints
  async getSettingsSections(): Promise<SettingsSectionsResponse> {
    const response = await this.client.get<SettingsSectionsResponse>('/settings/sections');
    return response.data;
  }

  async getSettingsSection(sectionName: string): Promise<SettingsSectionResponse> {
    return this.deduplicatedGet<SettingsSectionResponse>(`/settings/section/${sectionName}`);
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async updateSettingsSection(sectionName: string, config: any): Promise<SettingsUpdateResponse> {
    const response = await this.client.put<SettingsUpdateResponse>(`/settings/section/${sectionName}`, { config });
    return response.data;
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async testConnection(service: string, config: any, useExisting: boolean = false): Promise<TestConnectionResponse> {
    const response = await this.client.post<TestConnectionResponse>(`/settings/test/${service}`, { config, use_existing: useExisting });
    return response.data;
  }

  async exportYAML(): Promise<ExportYAMLResponse> {
    const response = await this.client.get<ExportYAMLResponse>('/settings/export');
    return response.data;
  }

  async getConfigHistory(key?: string, limit: number = 100, onlyChanged: boolean = false): Promise<ConfigHistoryResponse> {
    const params = new URLSearchParams();
    if (key) params.append('key', key);
    params.append('limit', limit.toString());
    if (onlyChanged) params.append('only_changed', 'true');
    const response = await this.client.get<ConfigHistoryResponse>(`/settings/history?${params}`);
    return response.data;
  }

  async gatherLogs(): Promise<{ logs: string }> {
    const response = await this.client.get('/settings/gather-logs');
    return response.data;
  }

  // SNMP endpoints
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async discoverSNMPInterfaces(config: any): Promise<SNMPDiscoverResponse> {
    const response = await this.client.post<SNMPDiscoverResponse>('/settings/snmp/discover', { config });
    return response.data;
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async testSNMPConnection(config: any): Promise<TestConnectionResponse> {
    const response = await this.client.post<TestConnectionResponse>('/settings/test/snmp', { config });
    return response.data;
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async pollSNMPSpeeds(config: any, interfaceIndices: number[]): Promise<SNMPSpeedResponse> {
    const response = await this.client.post<SNMPSpeedResponse>('/settings/snmp/poll-speeds', {
      config,
      interface_indices: interfaceIndices,
    });
    return response.data;
  }

  // Download Clients endpoints
  async getDownloadClients(): Promise<{
    clients: Array<{
      id: string;
      type: string;
      name: string;
      enabled: boolean;
      url: string;
      username?: string;
      password?: string;
      api_key?: string;
      max_speed_mbps?: number;
      color: string;
      supports_upload: boolean;
    }>;
  }> {
    const response = await this.client.get('/settings/download-clients');
    return response.data;
  }

  async updateDownloadClients(clients: Array<{
    id: string;
    type: string;
    name: string;
    enabled: boolean;
    url: string;
    username?: string;
    password?: string;
    api_key?: string;
    max_speed_mbps?: number;
    color: string;
    supports_upload: boolean;
  }>): Promise<{
    clients: Array<{
      id: string;
      type: string;
      name: string;
      enabled: boolean;
      url: string;
      username?: string;
      password?: string;
      api_key?: string;
      max_speed_mbps?: number;
      color: string;
      supports_upload: boolean;
    }>;
    connection_results?: Record<string, boolean>;
  }> {
    const response = await this.client.put('/settings/download-clients', { clients });
    return response.data;
  }

  // Temporary Limits endpoints
  async getTemporaryLimits(): Promise<{
    active: boolean;
    download_mbps: number | null;
    upload_mbps: number | null;
    expires_at: string | null;
    remaining_minutes: number | null;
  }> {
    return this.deduplicatedGet('/bandwidth/temporary-limits');
  }

  async setTemporaryLimits(params: {
    download_mbps?: number | null;
    upload_mbps?: number | null;
    duration_hours: number;
  }): Promise<{
    active: boolean;
    download_mbps: number | null;
    upload_mbps: number | null;
    expires_at: string | null;
    remaining_minutes: number | null;
  }> {
    const response = await this.client.post('/bandwidth/temporary-limits', params);
    return response.data;
  }

  async clearTemporaryLimits(): Promise<{ message: string; active: boolean }> {
    const response = await this.client.delete('/bandwidth/temporary-limits');
    return response.data;
  }

  // Bandwidth reservations
  async getBandwidthReservations(): Promise<{
    reservations: Array<{
      id: string;
      bandwidth_mbps: number;
      user_id: string;
      player: string;
      user_name: string;
      media_title: string;
      start_time: string;
      duration_seconds: number;
      expires_at: string;
    }>;
    total_reserved_mbps: number;
    count: number;
  }> {
    const response = await this.client.get('/bandwidth/reservations');
    return response.data;
  }

  async clearBandwidthReservation(reservationId: string): Promise<{ message: string; reservation_id: string }> {
    const response = await this.client.delete(`/bandwidth/reservations/${encodeURIComponent(reservationId)}`);
    return response.data;
  }

  // Setup wizard endpoints
  async initializeConfig(): Promise<{ success: boolean; message: string }> {
    const response = await this.client.post('/settings/initialize-config');
    return response.data;
  }

  async completeSetup(): Promise<{ success: boolean; message: string }> {
    const response = await this.client.post('/settings/complete-setup');
    return response.data;
  }
}

// Export singleton instance
export const apiClient = new ApiClient();
