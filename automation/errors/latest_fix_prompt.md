Fix this error in the valuation MVP.

User-visible problem:
- Vi kunde inte läsa eller behandla underlaget i det här försöket.

Debug context:
- debug_id: `vision_80c99ced5a30`
- stage: `image_decode`
- status: `error`
- technical_message: image_preprocess_failed: Image bytes could not be decoded. (request_id=vision_80c99ced5a30)

Safe reproduction summary:
```json
{
  "image_count": 3,
  "has_image_payload": true,
  "brand_override_present": false,
  "model_override_present": false,
  "filename_present": true
}
```

Relevant files to inspect:
- `88def0e5-dd48-4b14-87ea-8b34b9adc6d6.avif`
- `backend/app/services/image_preprocess.py`
- `backend/app/services/vision_service.py`

Suggested investigation area:
- Check base64 parsing, MIME handling, HEIC conversion, and Pillow decode/conversion paths.

Reproduction hints:
- Repeat the request with 3 uploaded image(s).
- Use the same file name again to confirm the failure is reproducible.
- Copy this report into Codex and ask it to fix the failing stage.

Constraints:
- Keep the fix lightweight and safe.
- Do not log secrets or huge payloads.
- Preserve API compatibility unless a small change is clearly necessary.

Please inspect the failing stage, explain the root cause, implement the smallest safe fix, and summarize changed files and verification.
