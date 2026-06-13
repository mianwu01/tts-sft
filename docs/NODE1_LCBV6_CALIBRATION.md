# Node 1 — LCBV6 BoN Calibration

Independent BoN, N=16, temperature=1.0, top_p=0.95, top_k=20, max_tokens=32768. Model: Qwen/Qwen3-4B-Thinking-2507.
Hidden (private) test suite; tests used for OFFLINE evaluation only (no test feedback during generation).

- **Total LCBV6 problems:** 131
- **saturated_easy** (16/16): 5
- **informative** (1–15/16): 84
- **hard_zero** (0/16, clean): 42
- **bad_truncated_or_bad_format** (0/16, capped/no-code): 0

- **Code-extraction:** 2089/2096 rows (99.7%)
- **Cap-hit (finish_reason=length):** 14/2096 rows (0.7%)
- **Tokens:** input 1,181,536 + output 29,214,422 = 30,395,958

- **Recommended default subset for SE/BoN comparison:** `lcbv6_non_saturated` (126 problems)

## IDs removed as saturated_easy
  lcbv6-026, lcbv6-045, lcbv6-046, lcbv6-054, lcbv6-129

## informative IDs
  lcbv6-001, lcbv6-002, lcbv6-003, lcbv6-005, lcbv6-006, lcbv6-008, lcbv6-009, lcbv6-011, lcbv6-012, lcbv6-013, lcbv6-014, lcbv6-015, lcbv6-016, lcbv6-017, lcbv6-018, lcbv6-020, lcbv6-021, lcbv6-022, lcbv6-023, lcbv6-024, lcbv6-025, lcbv6-027, lcbv6-028, lcbv6-029, lcbv6-030, lcbv6-032, lcbv6-033, lcbv6-034, lcbv6-035, lcbv6-037, lcbv6-038, lcbv6-040, lcbv6-041, lcbv6-042, lcbv6-043, lcbv6-044, lcbv6-047, lcbv6-051, lcbv6-052, lcbv6-053, lcbv6-055, lcbv6-056, lcbv6-057, lcbv6-058, lcbv6-059, lcbv6-066, lcbv6-070, lcbv6-074, lcbv6-077, lcbv6-082, lcbv6-083, lcbv6-084, lcbv6-085, lcbv6-086, lcbv6-087, lcbv6-089, lcbv6-093, lcbv6-094, lcbv6-096, lcbv6-097, lcbv6-098, lcbv6-099, lcbv6-100, lcbv6-101, lcbv6-103, lcbv6-104, lcbv6-105, lcbv6-107, lcbv6-108, lcbv6-110, lcbv6-111, lcbv6-112, lcbv6-114, lcbv6-115, lcbv6-116, lcbv6-117, lcbv6-119, lcbv6-121, lcbv6-122, lcbv6-123, lcbv6-125, lcbv6-126, lcbv6-128, lcbv6-130

## hard_zero_clean IDs
  lcbv6-000, lcbv6-004, lcbv6-007, lcbv6-010, lcbv6-019, lcbv6-031, lcbv6-036, lcbv6-039, lcbv6-048, lcbv6-049, lcbv6-050, lcbv6-060, lcbv6-061, lcbv6-062, lcbv6-063, lcbv6-064, lcbv6-065, lcbv6-067, lcbv6-068, lcbv6-069, lcbv6-071, lcbv6-072, lcbv6-073, lcbv6-075, lcbv6-076, lcbv6-078, lcbv6-079, lcbv6-080, lcbv6-081, lcbv6-088, lcbv6-090, lcbv6-091, lcbv6-092, lcbv6-095, lcbv6-102, lcbv6-106, lcbv6-109, lcbv6-113, lcbv6-118, lcbv6-120, lcbv6-124, lcbv6-127

## bad_truncated_or_bad_format IDs
  (none)
