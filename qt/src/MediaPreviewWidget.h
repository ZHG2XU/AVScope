#pragma once

#include <QImage>
#include <QJsonObject>
#include <QWidget>

class QAudioOutput;
class QLabel;
class QMediaPlayer;
class QPainter;
class QPushButton;
class QSlider;
class QTimer;
class QVideoSink;
class QWheelEvent;
class QMouseEvent;

class MediaPreviewWidget final : public QWidget
{
    Q_OBJECT
public:
    explicit MediaPreviewWidget(QWidget *parent = nullptr);
    void setMedia(const QJsonObject &media);
    void setDarkTheme(bool dark);

signals:
    void stepRequested(int direction);

protected:
    void paintEvent(QPaintEvent *event) override;
    void resizeEvent(QResizeEvent *event) override;
    void wheelEvent(QWheelEvent *event) override;
    void mouseMoveEvent(QMouseEvent *event) override;

private:
    void loadVisual();
    void configureVideoPlayback();
    void updateVideoControls();
    void setVideoControlsVisible(bool visible);
    void seekVideo(qint64 offsetMilliseconds);
    void drawWaveform(QPainter &painter, const QRectF &area) const;
    void drawSummary(QPainter &painter, const QRectF &area) const;
    QString visualCaption() const;

    QJsonObject m_media;
    QJsonObject m_summary;
    QImage m_image;
    QImage m_videoFrame;
    QPushButton *m_previous = nullptr;
    QPushButton *m_next = nullptr;
    QPushButton *m_playPause = nullptr;
    QPushButton *m_rewind = nullptr;
    QPushButton *m_fastForward = nullptr;
    QSlider *m_progress = nullptr;
    QLabel *m_elapsedLabel = nullptr;
    QLabel *m_timeLabel = nullptr;
    QTimer *m_controlsHideTimer = nullptr;
    QMediaPlayer *m_player = nullptr;
    QAudioOutput *m_audioOutput = nullptr;
    QVideoSink *m_videoSink = nullptr;
    bool m_playableVideo = false;
    qreal m_zoom = 1.0;
    QString m_playbackError;
    bool m_controlsVisible = true;
    bool m_dark = true;
};
