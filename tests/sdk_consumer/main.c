#include <libavformat/avformat.h>
#include <libavutil/avutil.h>
#include <stdio.h>

int main(void)
{
    if (!avformat_version() || !avutil_version())
        return 1;
    puts(av_version_info());
    return 0;
}
