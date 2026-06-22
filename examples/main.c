#include <stdio.h>
#include <libavutil/avutil.h>
#include <libavutil/dict.h>
#include <libavutil/pixdesc.h>
#include <libavutil/samplefmt.h>
#include <libavutil/error.h>
#include <libavformat/avformat.h>
#include <libavcodec/avcodec.h>

static void print_metadata(const AVDictionary *metadata, const char *indent)
{
    const AVDictionaryEntry *tag = NULL;
#if LIBAVUTIL_VERSION_INT >= AV_VERSION_INT(58, 0, 0)
    while ((tag = av_dict_iterate(metadata, tag)))
#else
    while ((tag = av_dict_get(metadata, "", tag, AV_DICT_IGNORE_SUFFIX)))
#endif
        printf("%s  %s: %s\n", indent, tag->key, tag->value);
}

static void print_stream_info(AVStream *stream, int index)
{
    AVCodecParameters *par = stream->codecpar;
    const char *type_str = av_get_media_type_string(par->codec_type);
    const char *codec_name = avcodec_get_name(par->codec_id);
    const char *profile = NULL;

    if (!type_str)
        type_str = "unknown";

    printf("  Stream #%d", index);

    switch (par->codec_type) {
    case AVMEDIA_TYPE_VIDEO:
        profile = avcodec_profile_name(par->codec_id, par->profile);
        printf(": Video %s", codec_name);
        if (profile)
            printf(" (%s)", profile);
        printf(", %s", av_get_pix_fmt_name(par->format));
        printf(", %dx%d", par->width, par->height);
        if (par->bit_rate > 0)
            printf(", %lld kb/s", (long long)(par->bit_rate / 1000));
        break;
    case AVMEDIA_TYPE_AUDIO:
        profile = avcodec_profile_name(par->codec_id, par->profile);
        printf(": Audio %s", codec_name);
        if (profile)
            printf(" (%s)", profile);
        printf(", %d Hz", par->sample_rate);
        printf(", %d ch (%s)", par->ch_layout.nb_channels,
               av_get_sample_fmt_name(par->format));
        if (par->bit_rate > 0)
            printf(", %lld kb/s", (long long)(par->bit_rate / 1000));
        break;
    case AVMEDIA_TYPE_SUBTITLE:
        printf(": Subtitle %s", codec_name);
        break;
    default:
        printf(": %s %s", type_str, codec_name);
        break;
    }

    printf("\n");

    if (stream->metadata)
        print_metadata(stream->metadata, "    ");
}

int main(int argc, char *argv[])
{
    int ret;
    int nb_errors = 0;

    if (argc < 2) {
        fprintf(stderr, "Usage: ffmeta <input_file> [input_file ...]\n");
        fprintf(stderr, "Print media file metadata and stream information.\n");
        return 1;
    }

    printf("ffmeta - FFmpeg %s\n\n", av_version_info());

    for (int i = 1; i < argc; i++) {
        const char *filename = argv[i];
        AVFormatContext *fmt_ctx = NULL;

        ret = avformat_open_input(&fmt_ctx, filename, NULL, NULL);
        if (ret < 0) {
            fprintf(stderr, "Error: cannot open '%s': %s\n",
                    filename, av_err2str(ret));
            nb_errors++;
            continue;
        }

        ret = avformat_find_stream_info(fmt_ctx, NULL);
        if (ret < 0) {
            fprintf(stderr, "Error: cannot find stream info for '%s': %s\n",
                    filename, av_err2str(ret));
            avformat_close_input(&fmt_ctx);
            nb_errors++;
            continue;
        }

        printf("=== %s ===\n", filename);
        printf("  Format: %s (%s)\n",
               fmt_ctx->iformat->long_name
                   ? fmt_ctx->iformat->long_name
                   : fmt_ctx->iformat->name,
               fmt_ctx->iformat->name);

        if (fmt_ctx->duration != AV_NOPTS_VALUE) {
            int64_t secs = fmt_ctx->duration / AV_TIME_BASE;
            printf("  Duration: %02d:%02d:%02d.%02d\n",
                   (int)(secs / 3600),
                   (int)((secs % 3600) / 60),
                   (int)(secs % 60),
                   (int)((fmt_ctx->duration % AV_TIME_BASE)
                         / (AV_TIME_BASE / 100)));
        }

        if (fmt_ctx->bit_rate > 0)
            printf("  Bitrate: %lld kb/s\n",
                   (long long)(fmt_ctx->bit_rate / 1000));

        printf("  Streams: %d\n", fmt_ctx->nb_streams);

        for (int j = 0; j < fmt_ctx->nb_streams; j++)
            print_stream_info(fmt_ctx->streams[j], j);

        if (fmt_ctx->metadata)
            print_metadata(fmt_ctx->metadata, "  ");

        printf("\n");
        avformat_close_input(&fmt_ctx);
    }

    return nb_errors > 0 ? 1 : 0;
}
