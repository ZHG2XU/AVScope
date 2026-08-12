#pragma once

#include <QImage>
#include <QJsonObject>
#include <QWidget>

class QPainter;

class MediaPreviewWidget final : public QWidget
{
    Q_OBJECT
public:
    explicit MediaPreviewWidget(QWidget *parent = nullptr);
    void setMedia(const QJsonObject &media);
    void setDarkTheme(bool dark);

protected:
    void paintEvent(QPaintEvent *event) override;

private:
    void loadVisual();
    void drawWaveform(QPainter &painter, const QRectF &area) const;
    void drawSummary(QPainter &painter, const QRectF &area) const;
    QString visualCaption() const;

    QJsonObject m_media;
    QJsonObject m_summary;
    QImage m_image;
    bool m_dark = true;
};
