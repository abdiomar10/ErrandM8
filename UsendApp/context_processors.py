def notifications(request):
    if request.user.is_authenticated:
        try:
            unread = request.user.notifications.filter(is_read=False).count()
        except Exception:
            unread = 0
    else:
        unread = 0
    return {'unread': unread}
