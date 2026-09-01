import { getPage, postOne } from "./resources";
import type { Report, ReportRequest, TaskQueuedResponse } from "../types/api";

export const listReports = (page = 1) => getPage<Report>("/reports/", { page });

export const requestReport = (request: ReportRequest) =>
  postOne<TaskQueuedResponse, ReportRequest>("/reports/generate/", request);
