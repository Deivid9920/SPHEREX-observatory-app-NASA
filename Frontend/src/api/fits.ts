import {
  apiBaseUrl,
  getJson,
  isFiniteNumber,
  isRecordValue,
  postJson,
} from "./client";
import { runTemporalJob, type JobStatus, type TemporalResult } from "./temporal";

export type FitsModule =
  | "sky_explorer"
  | "temporal_vision"
  | "spectral_analysis"
  | "object_detection"
  | "discovery_catalog";

export type LocalSpatialWcs = {
  variant: string;
  structural_status: string;
  sip_status: string;
  astrometric_validation_status: string;
  finast: number | null;
  ctype: string[];
  warnings: string[];
};

export type LocalFitsFile = {
  file_id: string;
  relative_path: string;
  filename: string;
  size_bytes: number | null;
  sha256: string | null;
  consumers: FitsModule[];
  product_type: string | null;
  source: string | null;
  downloaded_at: string | null;
  ingested_at: string;
  duplicate_of: string | null;
  validation_status: string;
  validation_warnings: string[];
  hdu_count: number;
  observation: Record<string, unknown>;
  release: string | null;
  release_metadata_present: boolean;
  has_celestial_wcs: boolean;
  has_spectral_wcs: boolean;
  metadata_presence: Record<string, string>;
  spatial_center: { ra: number; dec: number } | null;
  spatial_wcs?: LocalSpatialWcs | null;
  astrometric_validation_status?: string | null;
  spectral_channel_count: number | null;
  compatibility: Record<string, { compatible: boolean; reason: string | null }>;
};

export type LocalFitsCatalog = {
  dataset_root: string;
  generated_at: string;
  total: number;
  files: LocalFitsFile[];
};

export type FitsHeaderCard = {
  keyword: string;
  value: string | number | boolean | null;
  comment: string;
};

export type CalibrationState =
  | "verified"
  | "partially_verified"
  | "unverified"
  | "missing"
  | "incompatible"
  | "not_applicable";

export type LocalCalibrationDiagnosis = {
  file_id: string;
  filename: string;
  sha256: string | null;
  overall_calibration_status: CalibrationState;
  spatial_wcs_status: CalibrationState;
  spectral_wcs_status: CalibrationState;
  photometric_status: CalibrationState;
  psf_status: CalibrationState;
  uncertainty_status: CalibrationState;
  provenance_status: CalibrationState;
  calibrations: Record<string, {
    status: CalibrationState;
    reason: string;
    calibration_ids?: string[];
    selected_product?: {
      calibration_id: string;
      filename: string;
      relative_path: string;
      sha256: string;
      calibration_status: CalibrationState;
      integrity_status: string;
      source_url?: string | null;
      calibration_product_metadata?: {
        version?: string;
        processing_date?: string;
        release?: string;
      };
    } | null;
  }>;
  operation_authorizations: Record<string, { authorized: boolean; status: string; reason: string }>;
  warnings: string[];
  calibration_policy: string;
};

export type FitsHduMetadata = {
  index: number;
  name: string | null;
  version: string | number | null;
  type: string;
  shape: number[] | null;
  dtype: string | null;
  has_celestial_wcs: boolean;
  has_spectral_wcs: boolean;
  spatial_center: { ra: number; dec: number } | null;
  spatial_wcs?: LocalSpatialWcs | null;
  unit: string | null;
  checksum_present: boolean;
  checksum_valid: boolean | null;
  datasum_present: boolean;
  datasum_valid: boolean | null;
  header_cards: FitsHeaderCard[];
};

export type LocalFitsMetadata = LocalFitsFile & {
  extensions: FitsHduMetadata[];
};

const fitsModules = new Set<string>([
  "sky_explorer",
  "temporal_vision",
  "spectral_analysis",
  "object_detection",
  "discovery_catalog",
]);

export type LocalSpectralMeasurement = {
  channel: number;
  wavelength_um: number;
  bandwidth_um?: number | null;
  flux: number | null;
  flux_error: number | null;
  flag: number;
  flag_bits?: number[];
  flag_names?: string[];
  excluded_flag_names?: string[];
  unknown_flag_bits?: number[];
  quality_status?: string;
  quality_warnings?: string[];
  is_valid_measurement: boolean;
  measurement_status: string;
  uncertainty_status: string;
};

export type LocalCoordinateProvenance = {
  input: {
    ra_deg: number;
    dec_deg: number;
    coordinate_system: string;
    reference_epoch: string | null;
  };
  source: {
    file_id: string;
    filename: string;
    relative_path: string;
    sha256: string;
    detector: number | null;
    hdu_index: number | null;
    hdu_name: string;
    observation_epoch: string | null;
  };
  pixel: {
    x_unrounded: number;
    y_unrounded: number;
    x_index: number;
    y_index: number;
    fits_x_1_based: number;
    fits_y_1_based: number;
    array_indexing: string;
  };
  pixel_center_sky: {
    ra_deg: number;
    dec_deg: number;
    status: string;
  };
  wcs: {
    identifier: string;
    variant: string;
    structural_status: string;
    sip_status: string;
    astrometric_validation_status: string;
    finast: number | null;
    ctype: string[];
    warnings: string[];
  };
  astrometric_validation_status: string;
  positional_uncertainty_arcsec: number | null;
  method: string;
  scientifically_validated: boolean;
  warnings: string[];
  processed_at: string;
};

export type LocalSpectralProfile = {
  run_id?: string;
  result_sha256?: string;
  file_id: string;
  filename: string;
  relative_path: string;
  sha256: string;
  product_type: string | null;
  release: string | null;
  ra: number;
  dec: number;
  pixel_x?: number;
  pixel_y?: number;
  detector?: number | null;
  astrometric_validation_status?: string;
  coordinate_provenance?: LocalCoordinateProvenance;
  measurement_type: string;
  extraction_method: string;
  algorithm_version?: string;
  wavelength_source: string;
  bandwidth_available?: boolean;
  bandwidth_unit?: string | null;
  unit: string;
  uncertainty_unit: string | null;
  uncertainty_available: boolean;
  uncertainty_status: string;
  quality_status?: string;
  calibration_status: string;
  calibration_profile?: LocalCalibrationDiagnosis;
  calibration_product_ids?: string[];
  valid_channel_count: number;
  channel_count: number;
  measurements: LocalSpectralMeasurement[];
  warnings: string[];
  processed_at: string;
  software_version: string;
};

function isCoordinateProvenance(value: unknown): value is LocalCoordinateProvenance {
  if (!isRecordValue(value)) return false;
  const input = isRecordValue(value.input) ? value.input : null;
  const source = isRecordValue(value.source) ? value.source : null;
  const pixel = isRecordValue(value.pixel) ? value.pixel : null;
  const pixelCenter = isRecordValue(value.pixel_center_sky) ? value.pixel_center_sky : null;
  const wcs = isRecordValue(value.wcs) ? value.wcs : null;
  return Boolean(
    input &&
      isFiniteNumber(input.ra_deg) &&
      isFiniteNumber(input.dec_deg) &&
      typeof input.coordinate_system === "string" &&
      (input.reference_epoch === null || typeof input.reference_epoch === "string") &&
      source &&
      typeof source.file_id === "string" &&
      typeof source.filename === "string" &&
      typeof source.relative_path === "string" &&
      typeof source.sha256 === "string" &&
      (source.detector === null || isFiniteNumber(source.detector)) &&
      (source.hdu_index === null || isFiniteNumber(source.hdu_index)) &&
      typeof source.hdu_name === "string" &&
      (source.observation_epoch === null || typeof source.observation_epoch === "string") &&
      pixel &&
      ["x_unrounded", "y_unrounded", "x_index", "y_index", "fits_x_1_based", "fits_y_1_based"]
        .every((field) => isFiniteNumber(pixel[field])) &&
      typeof pixel.array_indexing === "string" &&
      pixelCenter &&
      isFiniteNumber(pixelCenter.ra_deg) &&
      isFiniteNumber(pixelCenter.dec_deg) &&
      typeof pixelCenter.status === "string" &&
      wcs &&
      typeof wcs.identifier === "string" &&
      typeof wcs.variant === "string" &&
      typeof wcs.sip_status === "string" &&
      typeof wcs.astrometric_validation_status === "string" &&
      (wcs.finast === null || isFiniteNumber(wcs.finast)) &&
      Array.isArray(wcs.ctype) &&
      wcs.ctype.every((axis) => typeof axis === "string") &&
      Array.isArray(wcs.warnings) &&
      wcs.warnings.every((warning) => typeof warning === "string") &&
      typeof value.astrometric_validation_status === "string" &&
      (value.positional_uncertainty_arcsec === null ||
        isFiniteNumber(value.positional_uncertainty_arcsec)) &&
      typeof value.method === "string" &&
      typeof value.scientifically_validated === "boolean" &&
      Array.isArray(value.warnings) &&
      value.warnings.every((warning) => typeof warning === "string") &&
      typeof value.processed_at === "string",
  );
}

export type LocalFitsDetection = {
  run_id?: string;
  result_sha256?: string;
  status: string;
  file_id: string;
  filename: string;
  relative_path: string;
  sha256: string;
  threshold_sigma: number;
  fwhm_px: number;
  method: string;
  threshold_definition: string;
  candidate_scores_are_probabilities: false;
  detections: Array<{
    source_id: string;
    x: number;
    y: number;
    ra: number;
    dec: number;
    flux: number;
    peak: number;
    sharpness: number;
    roundness: number;
  }>;
  processed_at: string;
  software_version: string;
  calibration_profile?: LocalCalibrationDiagnosis;
  calibration_product_ids?: string[];
  warnings: string[];
};

function isLocalFitsFile(value: unknown): value is LocalFitsFile {
  return (
    isRecordValue(value) &&
    typeof value.file_id === "string" &&
    typeof value.relative_path === "string" &&
    typeof value.filename === "string" &&
    (value.size_bytes === null || isFiniteNumber(value.size_bytes)) &&
    (value.sha256 === null || typeof value.sha256 === "string") &&
    Array.isArray(value.consumers) &&
    value.consumers.every((module) => typeof module === "string" && fitsModules.has(module)) &&
    typeof value.validation_status === "string" &&
    isFiniteNumber(value.hdu_count) &&
    isRecordValue(value.observation) &&
    isRecordValue(value.metadata_presence) &&
    Object.values(value.metadata_presence).every((status) => typeof status === "string") &&
    (value.release === null || typeof value.release === "string") &&
    (value.spatial_center === null ||
      (isRecordValue(value.spatial_center) &&
        isFiniteNumber(value.spatial_center.ra) &&
        isFiniteNumber(value.spatial_center.dec))) &&
    (value.spatial_wcs === undefined ||
      value.spatial_wcs === null ||
      (isRecordValue(value.spatial_wcs) &&
        typeof value.spatial_wcs.variant === "string" &&
        typeof value.spatial_wcs.structural_status === "string" &&
        typeof value.spatial_wcs.sip_status === "string" &&
        typeof value.spatial_wcs.astrometric_validation_status === "string" &&
        (value.spatial_wcs.finast === null || isFiniteNumber(value.spatial_wcs.finast)) &&
        Array.isArray(value.spatial_wcs.ctype) &&
        value.spatial_wcs.ctype.every((axis) => typeof axis === "string") &&
        Array.isArray(value.spatial_wcs.warnings) &&
        value.spatial_wcs.warnings.every((warning) => typeof warning === "string"))) &&
    (value.astrometric_validation_status === undefined ||
      value.astrometric_validation_status === null ||
      typeof value.astrometric_validation_status === "string") &&
    (value.spectral_channel_count === null || isFiniteNumber(value.spectral_channel_count)) &&
    Array.isArray(value.validation_warnings) &&
    value.validation_warnings.every((warning) => typeof warning === "string") &&
    isRecordValue(value.compatibility) &&
    Object.values(value.compatibility).every(
      (item) =>
        isRecordValue(item) &&
        typeof item.compatible === "boolean" &&
        (item.reason === null || typeof item.reason === "string"),
    )
  );
}

function isCatalog(value: unknown): value is LocalFitsCatalog {
  return (
    isRecordValue(value) &&
    typeof value.dataset_root === "string" &&
    typeof value.generated_at === "string" &&
    isFiniteNumber(value.total) &&
    Array.isArray(value.files) &&
    value.files.every(isLocalFitsFile)
  );
}

export function getLocalFitsFiles(module: FitsModule, signal?: AbortSignal) {
  const params = new URLSearchParams({ module });
  return getJson(`/data/fits?${params}`, isCatalog, { signal });
}

function isFitsMetadata(value: unknown): value is LocalFitsMetadata {
  const record = isRecordValue(value) ? value : null;
  if (!record) return false;
  const extensions = record.extensions;
  if (!isLocalFitsFile(record) || !Array.isArray(extensions)) return false;
  const extensionList: unknown[] = extensions;
  return extensionList.every(
    (hdu) =>
      isRecordValue(hdu) &&
      isFiniteNumber(hdu.index) &&
      typeof hdu.type === "string" &&
      (hdu.name === null || typeof hdu.name === "string") &&
      (hdu.shape === null || (Array.isArray(hdu.shape) && hdu.shape.every(isFiniteNumber))) &&
      typeof hdu.has_celestial_wcs === "boolean" &&
      typeof hdu.has_spectral_wcs === "boolean" &&
      (hdu.spatial_center === null ||
        (isRecordValue(hdu.spatial_center) &&
          isFiniteNumber(hdu.spatial_center.ra) &&
          isFiniteNumber(hdu.spatial_center.dec))) &&
      (hdu.spatial_wcs === undefined ||
        hdu.spatial_wcs === null ||
        (isRecordValue(hdu.spatial_wcs) &&
          typeof hdu.spatial_wcs.variant === "string" &&
            typeof hdu.spatial_wcs.structural_status === "string" &&
          typeof hdu.spatial_wcs.sip_status === "string" &&
          typeof hdu.spatial_wcs.astrometric_validation_status === "string")) &&
      (hdu.checksum_valid === null || typeof hdu.checksum_valid === "boolean") &&
      (hdu.datasum_valid === null || typeof hdu.datasum_valid === "boolean") &&
      Array.isArray(hdu.header_cards) &&
      hdu.header_cards.every(
        (card) =>
          isRecordValue(card) &&
          typeof card.keyword === "string" &&
          typeof card.comment === "string" &&
          (card.value === null ||
            typeof card.value === "string" ||
            typeof card.value === "number" ||
            typeof card.value === "boolean"),
      ),
  );
}

export function getFitsMetadata(fileId: string, signal?: AbortSignal) {
  return getJson(`/data/fits/${encodeURIComponent(fileId)}`, isFitsMetadata, { signal });
}

function isCalibrationDiagnosis(value: unknown): value is LocalCalibrationDiagnosis {
  return (
    isRecordValue(value) &&
    typeof value.file_id === "string" &&
    typeof value.filename === "string" &&
    (value.sha256 === null || typeof value.sha256 === "string") &&
    typeof value.overall_calibration_status === "string" &&
    typeof value.spatial_wcs_status === "string" &&
    typeof value.spectral_wcs_status === "string" &&
    typeof value.photometric_status === "string" &&
    typeof value.psf_status === "string" &&
    typeof value.uncertainty_status === "string" &&
    typeof value.provenance_status === "string" &&
    isRecordValue(value.calibrations) &&
    Object.values(value.calibrations).every(
      (item) =>
        isRecordValue(item) &&
        typeof item.status === "string" &&
        typeof item.reason === "string" &&
        (item.calibration_ids === undefined ||
          (Array.isArray(item.calibration_ids) &&
            item.calibration_ids.every((id) => typeof id === "string"))) &&
        (item.selected_product === undefined ||
          item.selected_product === null ||
          (isRecordValue(item.selected_product) &&
            typeof item.selected_product.calibration_id === "string" &&
            typeof item.selected_product.filename === "string" &&
            typeof item.selected_product.relative_path === "string" &&
            typeof item.selected_product.sha256 === "string" &&
            typeof item.selected_product.calibration_status === "string" &&
            typeof item.selected_product.integrity_status === "string")),
    ) &&
    isRecordValue(value.operation_authorizations) &&
    Object.values(value.operation_authorizations).every(
      (item) =>
        isRecordValue(item) &&
        typeof item.authorized === "boolean" &&
        typeof item.status === "string" &&
        typeof item.reason === "string",
    ) &&
    Array.isArray(value.warnings) &&
    value.warnings.every((warning) => typeof warning === "string") &&
    typeof value.calibration_policy === "string"
  );
}

export function getLocalCalibrationDiagnosis(fileId: string, signal?: AbortSignal) {
  return getJson(
    `/data/fits/${encodeURIComponent(fileId)}/calibration`,
    isCalibrationDiagnosis,
    { signal },
  );
}

export function getFitsPreviewUrl(fileId: string, hdu?: number, plane = 0) {
  const search = new URLSearchParams({ plane: String(plane) });
  if (hdu !== undefined) search.set("hdu", String(hdu));
  const params = `?${search}`;
  return `${apiBaseUrl}/api/v1/data/fits/${encodeURIComponent(fileId)}/preview${params}`;
}

export function getFitsDownloadUrl(fileId: string) {
  return `${apiBaseUrl}/api/v1/data/fits/${encodeURIComponent(fileId)}/download`;
}

export function getLocalSpectralPoint(fileId: string, ra: number, dec: number, signal?: AbortSignal) {
  const params = new URLSearchParams({ ra: String(ra), dec: String(dec) });
  return postJson(
    `/data/fits/${encodeURIComponent(fileId)}/spectral-runs?${params}`,
    {},
    isSpectralProfile,
    { signal, timeoutMs: 120_000 },
  );
}

function isSpectralProfile(value: unknown): value is LocalSpectralProfile {
  return (
    isRecordValue(value) &&
    typeof value.file_id === "string" &&
    typeof value.filename === "string" &&
    typeof value.relative_path === "string" &&
    typeof value.sha256 === "string" &&
    typeof value.measurement_type === "string" &&
    typeof value.extraction_method === "string" &&
    typeof value.wavelength_source === "string" &&
    (value.bandwidth_available === undefined || typeof value.bandwidth_available === "boolean") &&
    (value.bandwidth_unit === undefined || value.bandwidth_unit === null || typeof value.bandwidth_unit === "string") &&
    isFiniteNumber(value.ra) &&
    isFiniteNumber(value.dec) &&
    (value.detector === undefined ||
      value.detector === null ||
      isFiniteNumber(value.detector)) &&
    (value.astrometric_validation_status === undefined ||
      typeof value.astrometric_validation_status === "string") &&
    (value.coordinate_provenance === undefined ||
      isCoordinateProvenance(value.coordinate_provenance)) &&
    typeof value.unit === "string" &&
    (value.uncertainty_unit === null || typeof value.uncertainty_unit === "string") &&
    typeof value.uncertainty_available === "boolean" &&
    typeof value.uncertainty_status === "string" &&
    typeof value.calibration_status === "string" &&
    (value.calibration_profile === undefined || isCalibrationDiagnosis(value.calibration_profile)) &&
    (value.calibration_product_ids === undefined ||
      (Array.isArray(value.calibration_product_ids) &&
        value.calibration_product_ids.every((id) => typeof id === "string"))) &&
    isFiniteNumber(value.valid_channel_count) &&
    isFiniteNumber(value.channel_count) &&
    Array.isArray(value.measurements) &&
    value.measurements.every(
      (item) =>
        isRecordValue(item) &&
        isFiniteNumber(item.channel) &&
        isFiniteNumber(item.wavelength_um) &&
        (item.bandwidth_um === undefined ||
          item.bandwidth_um === null ||
          isFiniteNumber(item.bandwidth_um)) &&
        (item.flux === null || isFiniteNumber(item.flux)) &&
        (item.flux_error === null || isFiniteNumber(item.flux_error)) &&
        isFiniteNumber(item.flag) &&
        typeof item.is_valid_measurement === "boolean" &&
        typeof item.measurement_status === "string" &&
        typeof item.uncertainty_status === "string",
    ) &&
    Array.isArray(value.warnings) &&
    value.warnings.every((warning) => typeof warning === "string") &&
    typeof value.processed_at === "string" &&
    typeof value.software_version === "string"
  );
}

export function getLocalFitsDetections(
  fileId: string,
  thresholdSigma = 5,
  signal?: AbortSignal,
) {
  const params = new URLSearchParams({ threshold_sigma: String(thresholdSigma) });
  return postJson(
    `/data/fits/${encodeURIComponent(fileId)}/detection-runs?${params}`,
    {},
    isLocalFitsDetection,
    { signal, timeoutMs: 120_000 },
  );
}

export type StoredScientificRun<T> = {
  run_id: string;
  run_type: string;
  result: T;
};

function isStoredRun<T>(
  value: unknown,
  runType: string,
  isResult: (result: unknown) => result is T,
): value is StoredScientificRun<T> {
  return (
    isRecordValue(value) &&
    typeof value.run_id === "string" &&
    value.run_type === runType &&
    isResult(value.result)
  );
}

export function getStoredSpectralRun(runId: string, signal?: AbortSignal) {
  return getJson(
    `/data/scientific-runs/${encodeURIComponent(runId)}`,
    (value): value is StoredScientificRun<LocalSpectralProfile> =>
      isStoredRun(value, "spectral_extraction", isSpectralProfile),
    { signal },
  );
}

export function getStoredDetectionRun(runId: string, signal?: AbortSignal) {
  return getJson(
    `/data/scientific-runs/${encodeURIComponent(runId)}`,
    (value): value is StoredScientificRun<LocalFitsDetection> =>
      isStoredRun(value, "source_detection", isLocalFitsDetection),
    { signal, timeoutMs: 120_000 },
  );
}

function isLocalFitsDetection(value: unknown): value is LocalFitsDetection {
  return (
    isRecordValue(value) &&
    typeof value.status === "string" &&
    typeof value.file_id === "string" &&
    typeof value.filename === "string" &&
    typeof value.relative_path === "string" &&
    typeof value.sha256 === "string" &&
    isFiniteNumber(value.threshold_sigma) &&
    isFiniteNumber(value.fwhm_px) &&
    typeof value.method === "string" &&
    value.candidate_scores_are_probabilities === false &&
    Array.isArray(value.detections) &&
    value.detections.every(
      (item) =>
        isRecordValue(item) &&
        typeof item.source_id === "string" &&
        ["x", "y", "ra", "dec", "flux", "peak", "sharpness", "roundness"].every(
          (field) => isFiniteNumber(item[field]),
        ),
    ) &&
    typeof value.processed_at === "string" &&
    typeof value.software_version === "string" &&
    (value.calibration_profile === undefined || isCalibrationDiagnosis(value.calibration_profile)) &&
    (value.calibration_product_ids === undefined ||
      (Array.isArray(value.calibration_product_ids) &&
        value.calibration_product_ids.every((id) => typeof id === "string"))) &&
    Array.isArray(value.warnings) &&
    value.warnings.every((warning) => typeof warning === "string")
  );
}

export function runLocalTemporalComparison(
  input: {
    file_id_t1: string;
    file_id_t2: string;
    ra: number;
    dec: number;
  },
  signal?: AbortSignal,
  onProgress?: (status: JobStatus) => void,
): Promise<TemporalResult> {
  return runTemporalJob("/jobs/temporal/local", input, signal, onProgress);
}
