#pragma once

#include <QImage>
#include <QJsonObject>
#include <QWidget>

class QPainter;
class QPushButton;

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

private:
    void loadVisual();
    void drawWaveform(QPainter &painter, const QRectF &area) const;
    void drawSummary(QPainter &painter, const QRectF &area) const;
    QString visualCaption() const;

    QJsonObject m_media;
    QJsonObject m_summary;
    QImage m_image;
    QPushButton *m_previous = nullptr;
    QPushButton *m_next = nullptr;
    bool m_dark = true;
};
