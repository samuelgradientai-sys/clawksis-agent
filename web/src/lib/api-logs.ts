// Logs API shapes (clawk_cli/web_routers/logs.py).

export interface LogsResponse {
  file: string;
  lines: string[];
}

/** One entry of GET /api/logs/files: every log `clawk logs` knows, for the selected profile. */
export interface LogFileInfo {
  name: string;
  filename: string;
  exists: boolean;
  size: number | null;
  mtime: number | null;
  /** Written to the root home whatever profile is active (`update`, `handoff`). */
  root_home: boolean;
}

export interface LogFilesResponse {
  files: LogFileInfo[];
  components: string[];
}
