#pragma once

#include <QJsonArray>
#include <QWidget>

class TimelineWidget final : public QWidget
{
    Q_OBJECT
public:
    explicit TimelineWidget(QWidget *parent = nullptr);
    void setFrames(const QJsonArray &frames);
    void setDarkTheme(bool dark);

protected:
    void paintEvent(QPaintEvent *event) override;

private:
    QJsonArray m_frames;
    bool m_dark = true;
};
