Fix this error in the valuation MVP.

User-visible problem:
- Vi kunde inte läsa eller behandla underlaget i det här försöket.

Debug context:
- debug_id: `vision_513771133b65`
- stage: `upload`
- status: `error`
- technical_message: no_images_provided: At least one uploaded image is required for identification. (request_id=vision_513771133b65)

Safe reproduction summary:
```json
{
  "image_count": 0,
  "has_image_payload": false,
  "brand_override_present": false,
  "model_override_present": false,
  "filename_present": false
}
```

Relevant files to inspect:
- `frontend/index.html`
- `backend/app/api/value.py`

Suggested investigation area:
- Check request validation and missing-image handling between the frontend submit flow and /value route.

Reproduction hints:
- Repeat the request and confirm whether any image was uploaded.
- Copy this report into Codex and ask it to fix the failing stage.

Constraints:
- Keep the fix lightweight and safe.
- Do not log secrets or huge payloads.
- Preserve API compatibility unless a small change is clearly necessary.

Please inspect the failing stage, explain the root cause, implement the smallest safe fix, and summarize changed files and verification.
