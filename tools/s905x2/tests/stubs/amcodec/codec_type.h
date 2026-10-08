#pragma once
// Only the fields read by the stream guard. Production uses libamcodec headers.
enum { VFORMAT_HEVC = 11 };
struct codec_para_t { bool has_video; bool dv_enable; int video_type; };
