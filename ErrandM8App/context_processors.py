def notifications(request):
    if request.user.is_authenticated:
        unread = request.user.notifications.filter(is_read=False).count()
    else:
        unread = 0
    return {'unread': unread}
