#include "MediaPreviewWidget.h"

#include <QAudioOutput>
#include <QFileInfo>
#include <QJsonArray>
#include <QIcon>
#include <QLabel>
#include <QMediaPlayer>
#include <QMouseEvent>
#include <QPainter>
#include <QPainterPath>
#include <QPushButton>
#include <QResizeEvent>
#include <QSignalBlocker>
#include <QSlider>
#include <QTimer>
#include <QUrl>
#include <QVideoFrame>
#include <QVideoSink>
#include <QWheelEvent>

#include <limits>

namespace {
QString scalarText(const QJsonValue &value)
{
    if (value.isString()) return value.toString();
    if (value.isDouble()) return QString::number(value.toDouble(), 'g', 8);
    if (value.isBool()) return value.toBool() ? QObject::tr("是") : QObject::tr("否");
    return {};
}
}

MediaPreviewWidget::MediaPreviewWidget(QWidget *parent) : QWidget(parent)
{
    setMinimumSize(480, 320);
    setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
    setMouseTracking(true);
    m_previous = new QPushButton("<", this);
    m_next = new QPushButton(">", this);
    m_rewind = new QPushButton(this);
    m_playPause = new QPushButton(this);
    m_fastForward = new QPushButton(this);
    for (auto *button : {m_previous, m_next, m_rewind, m_playPause, m_fastForward}) {
        button->setFixedHeight(30);
        button->setVisible(false);
    }
    m_previous->setFixedWidth(34);
    m_next->setFixedWidth(34);
    m_rewind->setFixedSize(44, 44);
    m_playPause->setFixedSize(48, 48);
    m_fastForward->setFixedSize(44, 44);
    for (auto *button : {m_rewind, m_playPause, m_fastForward}) {
        button->setFlat(true);
        button->setIconSize(QSize(30, 30));
    }
    m_rewind->setObjectName("videoControl");
    m_fastForward->setObjectName("videoControl");
    m_playPause->setObjectName("videoPlayControl");
    m_rewind->setStyleSheet(
        "QPushButton#videoControl { background: rgba(9, 13, 18, 112); border: 1px solid rgba(255,255,255,74); "
        "border-radius: 22px; padding: 0; } "
        "QPushButton#videoControl:hover { background: rgba(255,255,255,42); border-color: rgba(255,255,255,165); } "
        "QPushButton#videoControl:pressed { background: rgba(255,255,255,68); border-color: rgba(255,255,255,210); } "
        "QPushButton#videoControl:disabled { background: rgba(9, 13, 18, 55); border-color: rgba(255,255,255,30); }");
    m_fastForward->setStyleSheet(m_rewind->styleSheet());
    m_playPause->setStyleSheet(
        "QPushButton#videoPlayControl { background: rgba(255,255,255,42); border: 1px solid rgba(255,255,255,115); border-radius: 24px; padding: 0; } "
        "QPushButton#videoPlayControl:hover { background: rgba(255,255,255,72); border-color: rgba(255,255,255,190); } "
        "QPushButton#videoPlayControl:pressed { background: rgba(255,255,255,100); border-color: rgba(255,255,255,230); }");
    m_rewind->setIcon(QIcon(":/icons/skip-back-10.svg"));
    m_fastForward->setIcon(QIcon(":/icons/skip-forward-30.svg"));
    m_previous->setToolTip(tr("上一预览位置"));
    m_next->setToolTip(tr("下一预览位置"));
    m_rewind->setToolTip(tr("后退 10 秒"));
    m_fastForward->setToolTip(tr("前进 30 秒"));
    m_progress = new QSlider(Qt::Horizontal, this);
    m_progress->setVisible(false);
    m_progress->setToolTip(tr("拖动以定位播放位置"));
    connect(m_previous, &QPushButton::clicked, this, [this] { emit stepRequested(-1); });
    connect(m_next, &QPushButton::clicked, this, [this] { emit stepRequested(1); });
    connect(m_rewind, &QPushButton::clicked, this, [this] { seekVideo(-10000); });
    connect(m_fastForward, &QPushButton::clicked, this, [this] { seekVideo(30000); });
    connect(m_playPause, &QPushButton::clicked, this, [this] {
        if (m_player->playbackState() == QMediaPlayer::PlayingState) m_player->pause();
        else m_player->play();
    });
    connect(m_progress, &QSlider::sliderMoved, this, [this](int position) {
        if (m_playableVideo && m_player->duration() > 0) m_player->setPosition(position);
    });
    m_elapsedLabel = new QLabel(this);
    m_elapsedLabel->setAlignment(Qt::AlignLeft | Qt::AlignVCenter);
    m_elapsedLabel->setStyleSheet("color: #E7EDF3;");
    m_elapsedLabel->setVisible(false);
    m_timeLabel = new QLabel(this);
    m_timeLabel->setAlignment(Qt::AlignRight | Qt::AlignVCenter);
    m_timeLabel->setStyleSheet("color: #E7EDF3;");
    m_timeLabel->setVisible(false);
    m_controlsHideTimer = new QTimer(this);
    m_controlsHideTimer->setSingleShot(true);
    m_controlsHideTimer->setInterval(1800);
    connect(m_controlsHideTimer, &QTimer::timeout, this, [this] {
        if (m_player->playbackState() == QMediaPlayer::PlayingState) setVideoControlsVisible(false);
    });

    m_player = new QMediaPlayer(this);
    m_audioOutput = new QAudioOutput(this);
    m_videoSink = new QVideoSink(this);
    m_player->setAudioOutput(m_audioOutput);
    m_player->setVideoOutput(m_videoSink);
    connect(m_videoSink, &QVideoSink::videoFrameChanged, this, [this](const QVideoFrame &frame) {
        if (!frame.isValid()) return;
        m_videoFrame = frame.toImage();
        update();
    });
    connect(m_player, &QMediaPlayer::playbackStateChanged, this, [this] {
        setVideoControlsVisible(true);
        updateVideoControls();
        if (m_player->playbackState() == QMediaPlayer::PlayingState) m_controlsHideTimer->start();
        else m_controlsHideTimer->stop();
    });
    connect(m_player, &QMediaPlayer::positionChanged, this, [this] {
        updateVideoControls();
        update();
    });
    connect(m_player, &QMediaPlayer::durationChanged, this, [this] { updateVideoControls(); });
    connect(m_player, &QMediaPlayer::errorOccurred, this, [this](QMediaPlayer::Error, const QString &message) {
        m_playbackError = message;
        update();
    });
}

void MediaPreviewWidget::setMedia(const QJsonObject &media)
{
    m_media = media;
    m_summary = media.value("summary").toObject();
    m_zoom = 1.0;
    m_controlsVisible = true;
    m_playbackError.clear();
    loadVisual();
    configureVideoPlayback();
    const bool navigable = !m_playableVideo && !m_image.isNull()
        && (m_summary.contains("yuv_preview") || m_summary.contains("video_preview"));
    m_previous->setVisible(navigable);
    m_next->setVisible(navigable);
    if (m_summary.contains("yuv_preview")) {
        const auto preview = m_summary.value("yuv_preview").toObject();
        const int frame = preview.value("frame_index").toInt();
        const int total = preview.value("total_frames").toInt();
        m_previous->setEnabled(frame > 0);
        m_next->setEnabled(frame + 1 < total);
    } else if (navigable) {
        m_previous->setEnabled(m_summary.value("video_preview").toObject().value("position_seconds").toDouble() > 0.0);
        m_next->setEnabled(true);
    }
    if (m_playableVideo) {
        const int controlsTop = height() - 92;
        const int controlsCenterY = height() - 28;
        const int center = width() / 2;
        m_elapsedLabel->setGeometry(18, controlsTop + 10, 52, 20);
        m_timeLabel->setGeometry(width() - 70, controlsTop + 10, 52, 20);
        m_progress->setGeometry(78, controlsTop + 9, qMax(80, width() - 156), 20);
        m_rewind->move(center - 78, controlsCenterY - m_rewind->height() / 2);
        m_playPause->move(center - m_playPause->width() / 2, controlsCenterY - m_playPause->height() / 2);
        m_fastForward->move(center + 34, controlsCenterY - m_fastForward->height() / 2);
    }
    update();
}

void MediaPreviewWidget::setDarkTheme(bool dark)
{
    m_dark = dark;
    update();
}

void MediaPreviewWidget::loadVisual()
{
    m_image = {};
    for (const QString &key : {QString("video_preview"), QString("yuv_preview")}) {
        const auto preview = m_summary.value(key).toObject();
        const QString path = preview.value("path").toString();
        if (preview.value("available").toBool() && QFileInfo::exists(path) && m_image.load(path)) return;
    }
}

void MediaPreviewWidget::configureVideoPlayback()
{
    m_player->stop();
    m_player->setSource({});
    m_videoFrame = {};
    m_playableVideo = false;
    for (const auto &stream : m_summary.value("ffprobe").toObject().value("streams").toArray()) {
        if (stream.toObject().value("codec_type").toString() == "video") {
            m_playableVideo = QFileInfo::exists(m_media.value("path").toString());
            break;
        }
    }
    if (m_playableVideo)
        m_player->setSource(QUrl::fromLocalFile(m_media.value("path").toString()));
    updateVideoControls();
}

void MediaPreviewWidget::updateVideoControls()
{
    const bool controlsVisible = m_playableVideo && m_controlsVisible;
    m_playPause->setVisible(controlsVisible);
    m_rewind->setVisible(controlsVisible);
    m_fastForward->setVisible(controlsVisible);
    m_progress->setVisible(controlsVisible);
    m_elapsedLabel->setVisible(controlsVisible);
    m_timeLabel->setVisible(controlsVisible);
    m_playPause->setIcon(QIcon(m_player->playbackState() == QMediaPlayer::PlayingState
        ? ":/icons/pause.svg" : ":/icons/play.svg"));
    const bool seekable = m_playableVideo && m_player->duration() > 0;
    m_rewind->setEnabled(seekable && m_player->position() > 0);
    m_fastForward->setEnabled(seekable && m_player->position() < m_player->duration());
    {
        QSignalBlocker blocker(m_progress);
        m_progress->setRange(0, seekable ? static_cast<int>(qMin<qint64>(m_player->duration(), std::numeric_limits<int>::max())) : 0);
        m_progress->setValue(seekable ? static_cast<int>(qMin<qint64>(m_player->position(), std::numeric_limits<int>::max())) : 0);
    }
    m_progress->setEnabled(seekable);
    const auto formatTime = [](qint64 milliseconds) {
        const qint64 seconds = qMax<qint64>(0, milliseconds / 1000);
        return QString("%1:%2").arg(seconds / 60, 2, 10, QLatin1Char('0')).arg(seconds % 60, 2, 10, QLatin1Char('0'));
    };
    m_elapsedLabel->setText(seekable ? formatTime(m_player->position()) : tr("--:--"));
    m_timeLabel->setText(seekable ? formatTime(m_player->duration()) : tr("--:--"));
}

void MediaPreviewWidget::setVideoControlsVisible(bool visible)
{
    if (m_controlsVisible == visible) return;
    m_controlsVisible = visible;
    updateVideoControls();
    update();
}

void MediaPreviewWidget::seekVideo(qint64 offsetMilliseconds)
{
    if (!m_playableVideo || m_player->duration() <= 0) return;
    m_player->setPosition(qBound<qint64>(0, m_player->position() + offsetMilliseconds, m_player->duration()));
}

void MediaPreviewWidget::paintEvent(QPaintEvent *)
{
    QPainter painter(this);
    painter.setRenderHint(QPainter::Antialiasing);
    painter.setRenderHint(QPainter::SmoothPixmapTransform);
    const QColor background = m_dark ? QColor("#121A22") : QColor("#FFFFFF");
    const QColor surface = m_dark ? QColor("#17212B") : QColor("#EDF2F6");
    const QColor text = m_dark ? QColor("#E7EDF3") : QColor("#172331");
    const QColor muted = m_dark ? QColor("#94A3B2") : QColor("#607080");
    const QColor border = m_dark ? QColor("#273442") : QColor("#D8E1E8");
    painter.fillRect(rect(), background);
    if (m_playableVideo) {
        painter.fillRect(rect(), Qt::black);
        const QImage &visual = !m_videoFrame.isNull() ? m_videoFrame : m_image;
        if (!visual.isNull()) {
            const QSizeF fitted = visual.size().scaled(size(), Qt::KeepAspectRatio);
            const QRectF target(width() / 2.0 - fitted.width() / 2.0, height() / 2.0 - fitted.height() / 2.0,
                                fitted.width(), fitted.height());
            painter.save();
            painter.setClipRect(rect());
            painter.drawImage(target, visual);
            painter.restore();
        } else if (!m_playbackError.isEmpty()) {
            painter.setPen(Qt::white);
            painter.drawText(rect(), Qt::AlignCenter, tr("视频播放失败：%1").arg(m_playbackError));
        }
        if (m_controlsVisible)
            painter.fillRect(0, height() - 92, width(), 92, QColor(12, 15, 20, 190));
        return;
    }
    const QRectF content = QRectF(rect()).adjusted(24, 20, -24, -20);
    QFont titleFont = font(); titleFont.setPointSize(15); titleFont.setBold(true);
    painter.setFont(titleFont); painter.setPen(text);
    painter.drawText(content.left(), content.top() + 20, m_media.value("format_name").toString(tr("媒体预览")));
    QFont captionFont = font(); captionFont.setPointSize(9);
    painter.setFont(captionFont); painter.setPen(muted);
    painter.drawText(content.left(), content.top() + 43, visualCaption());
    const QRectF visualArea(content.left(), content.top() + 62, content.width(), qMax<qreal>(150, content.height() * 0.57));
    QPainterPath panelPath; panelPath.addRoundedRect(visualArea, 6, 6);
    painter.fillPath(panelPath, surface); painter.setPen(QPen(border, 1)); painter.drawPath(panelPath);
    const QImage &visual = !m_videoFrame.isNull() ? m_videoFrame : m_image;
    if (!visual.isNull()) {
        QSizeF fitted = visual.size().scaled(visualArea.size().toSize() - QSize(30, 30), Qt::KeepAspectRatio);
        fitted *= m_zoom;
        const QRectF target(visualArea.center().x() - fitted.width() / 2.0, visualArea.center().y() - fitted.height() / 2.0, fitted.width(), fitted.height());
        painter.save(); painter.setClipRect(visualArea.adjusted(1, 1, -1, -1)); painter.drawImage(target, visual); painter.restore();
    } else if (m_summary.value("waveform").toObject().value("available").toBool()) {
        drawWaveform(painter, visualArea.adjusted(18, 16, -18, -16));
    } else if (m_summary.value("rtcp").toObject().value("available").toBool()) {
        painter.setPen(muted);
        painter.drawText(visualArea, Qt::AlignCenter, tr("RTCP 会话质量数据已解析\n可在下方摘要与协议树中查看报告详情"));
    } else {
        painter.setPen(muted);
        painter.drawText(visualArea, Qt::AlignCenter, m_playableVideo && !m_playbackError.isEmpty()
            ? tr("视频播放失败：%1").arg(m_playbackError) : tr("当前文件没有可解码画面或音频波形"));
    }
    const QRectF summaryArea(content.left(), visualArea.bottom() + 18, content.width(), qMax<qreal>(72, content.bottom() - visualArea.bottom() - 18));
    drawSummary(painter, summaryArea);
}

void MediaPreviewWidget::resizeEvent(QResizeEvent *event)
{
    QWidget::resizeEvent(event);
    if (m_playableVideo) {
        const int controlsTop = height() - 92;
        const int controlsCenterY = height() - 28;
        const int center = width() / 2;
        m_elapsedLabel->setGeometry(18, controlsTop + 10, 52, 20);
        m_timeLabel->setGeometry(width() - 70, controlsTop + 10, 52, 20);
        m_progress->setGeometry(78, controlsTop + 9, qMax(80, width() - 156), 20);
        m_rewind->move(center - 78, controlsCenterY - m_rewind->height() / 2);
        m_playPause->move(center - m_playPause->width() / 2, controlsCenterY - m_playPause->height() / 2);
        m_fastForward->move(center + 34, controlsCenterY - m_fastForward->height() / 2);
        return;
    }
    const int y = 18;
    m_next->move(width() - 24 - m_next->width(), y);
    m_previous->move(m_next->x() - 7 - m_previous->width(), y);
    const int contentHeight = height() - 40;
    const int visualTop = 82;
    const int visualHeight = qMax(150, static_cast<int>(contentHeight * 0.57));
    const int controlsY = visualTop + visualHeight - 34;
    m_playPause->move(42, controlsY);
    m_timeLabel->setGeometry(width() - 138, controlsY, 96, 30);
    m_progress->setGeometry(102, controlsY + 4, qMax(80, width() - 250), 22);
}

void MediaPreviewWidget::wheelEvent(QWheelEvent *event)
{
    if (!event->modifiers().testFlag(Qt::ControlModifier) || (m_image.isNull() && m_videoFrame.isNull())) {
        QWidget::wheelEvent(event);
        return;
    }
    m_zoom = qBound<qreal>(0.25, m_zoom * (event->angleDelta().y() > 0 ? 1.15 : 1.0 / 1.15), 4.0);
    event->accept();
    update();
}

void MediaPreviewWidget::mouseMoveEvent(QMouseEvent *event)
{
    if (m_playableVideo) {
        setVideoControlsVisible(true);
        if (m_player->playbackState() == QMediaPlayer::PlayingState) m_controlsHideTimer->start();
    }
    QWidget::mouseMoveEvent(event);
}

void MediaPreviewWidget::drawWaveform(QPainter &painter, const QRectF &area) const
{
    const auto peaks = m_summary.value("waveform").toObject().value("peaks").toArray();
    if (peaks.isEmpty()) return;
    const QColor grid = m_dark ? QColor("#2A3947") : QColor("#CFDAE3");
    const QColor axis = m_dark ? QColor("#637486") : QColor("#91A1B1");
    painter.setPen(QPen(grid, 1));
    for (int index = 1; index < 4; ++index) { const qreal y = area.top() + area.height() * index / 4.0; painter.drawLine(QPointF(area.left(), y), QPointF(area.right(), y)); }
    painter.setPen(QPen(axis, 1.2)); painter.drawLine(QPointF(area.left(), area.center().y()), QPointF(area.right(), area.center().y()));
    const qreal step = area.width() / qMax(1, peaks.size());
    for (int index = 0; index < peaks.size(); ++index) {
        const auto point = peaks.at(index).toObject(); const qreal x = area.left() + (index + .5) * step;
        painter.setPen(QPen(QColor("#36A7D8"), qMax<qreal>(1.2, step * .55), Qt::SolidLine, Qt::RoundCap));
        painter.drawLine(QPointF(x, area.center().y() - point.value("max").toDouble() * area.height() * .46), QPointF(x, area.center().y() - point.value("min").toDouble() * area.height() * .46));
    }
}

void MediaPreviewWidget::drawSummary(QPainter &painter, const QRectF &area) const
{
    const QColor surface = m_dark ? QColor("#17212B") : QColor("#EDF2F6");
    const QColor text = m_dark ? QColor("#E7EDF3") : QColor("#172331");
    const QColor muted = m_dark ? QColor("#94A3B2") : QColor("#607080");
    const QStringList keys = {"width", "height", "pixel_format", "fps", "sample_rate", "channels", "bits_per_sample", "duration"};
    const QStringList labels = {tr("宽度"), tr("高度"), tr("像素格式"), tr("帧率"), tr("采样率"), tr("声道"), tr("位深"), tr("时长")};
    QVector<QPair<QString, QString>> values;
    for (int index = 0; index < keys.size(); ++index) { const QString value = scalarText(m_summary.value(keys.at(index))); if (!value.isEmpty()) values.append({labels.at(index), value}); }
    const auto energy = m_summary.value("waveform").toObject().value("energy").toObject();
    if (!energy.isEmpty()) {
        values.append({"Peak", QString("%1 dBFS").arg(energy.value("peak_dbfs").toDouble(), 0, 'f', 2)});
        values.append({"RMS", QString("%1 dBFS").arg(energy.value("rms_dbfs").toDouble(), 0, 'f', 2)});
    }
    const auto rtcp = m_summary.value("rtcp").toObject();
    if (rtcp.value("available").toBool()) {
        values.append({tr("SR / RR"), QString("%1 / %2").arg(rtcp.value("sender_reports").toInt()).arg(rtcp.value("receiver_reports").toInt())});
        values.append({tr("最大丢包率"), QString("%1%").arg(rtcp.value("max_fraction_lost_percent").toDouble(), 0, 'f', 2)});
        values.append({tr("最大 Jitter"), QString::number(rtcp.value("max_interarrival_jitter").toInt())});
    }
    if (values.isEmpty()) values.append({tr("文件大小"), QString::number(m_media.value("size").toDouble()) + " B"});
    const int columns = qMin(4, values.size()); const qreal gap = 10; const qreal cardWidth = (area.width() - gap * (columns - 1)) / columns;
    QFont labelFont = font(); labelFont.setPointSize(8); QFont valueFont = font(); valueFont.setPointSize(11); valueFont.setBold(true);
    for (int index = 0; index < columns; ++index) {
        const QRectF card(area.left() + index * (cardWidth + gap), area.top(), cardWidth, qMin<qreal>(72, area.height()));
        painter.setPen(Qt::NoPen); painter.setBrush(surface); painter.drawRoundedRect(card, 5, 5);
        painter.setFont(labelFont); painter.setPen(muted); painter.drawText(card.adjusted(12, 9, -8, -8), Qt::AlignTop | Qt::AlignLeft, values.at(index).first);
        painter.setFont(valueFont); painter.setPen(text); painter.drawText(card.adjusted(12, 27, -8, -7), Qt::AlignTop | Qt::AlignLeft, values.at(index).second);
    }
}

QString MediaPreviewWidget::visualCaption() const
{
    if (!m_image.isNull() || !m_videoFrame.isNull()) {
        const auto preview = m_summary.value("video_preview").toObject().value("available").toBool() ? m_summary.value("video_preview").toObject() : m_summary.value("yuv_preview").toObject();
        QString detail = preview.value("pixel_format").toString();
        if (m_playableVideo && m_player->duration() > 0)
            detail += tr("  %1 / %2 s").arg(m_player->position() / 1000.0, 0, 'f', 1).arg(m_player->duration() / 1000.0, 0, 'f', 1);
        return tr("%1 × %2  %3  缩放 %4%").arg(preview.value("width").toInt()).arg(preview.value("height").toInt()).arg(detail).arg(qRound(m_zoom * 100));
    }
    const auto waveform = m_summary.value("waveform").toObject();
    if (waveform.value("available").toBool()) return tr("音频波形  %1 Hz  %2 声道").arg(waveform.value("sample_rate").toInt()).arg(waveform.value("channels").toInt());
    const auto rtcp = m_summary.value("rtcp").toObject();
    if (rtcp.value("available").toBool()) return tr("RTCP  %1 个控制包  %2 个报告块  %3 个 SSRC").arg(rtcp.value("packets").toInt()).arg(rtcp.value("report_blocks").toInt()).arg(rtcp.value("ssrcs").toArray().size());
    return tr("结构化媒体摘要");
}
