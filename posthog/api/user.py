from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth import update_session_auth_hash
from django.core.exceptions import ValidationError
from django.shortcuts import redirect
from django.conf import settings
from posthog.models import Event

import urllib.parse
import secrets
import json

def user(request):
    if not request.user.is_authenticated:
        return HttpResponse('Unauthorized', status=401)

    team = request.user.team_set.get()

    if request.method == 'PATCH':
        data = json.loads(request.body)
        team.app_urls = data['team'].get('app_urls', team.app_urls)
        team.opt_out_capture = data['team'].get('opt_out_capture', team.opt_out_capture)
        team.save()

    return JsonResponse({
        'id': request.user.pk,
        'distinct_id': request.user.distinct_id,
        'name': request.user.first_name,
        'email': request.user.email,
        'has_events': Event.objects.filter(team=team).exists(),
        'team': {
            'app_urls': team.app_urls,
            'api_token': team.api_token,
            'signup_token': team.signup_token,
            'opt_out_capture': team.opt_out_capture
        },
        'posthog_version': settings.VERSION if hasattr(settings, 'VERSION') else None
    })

def redirect_to_site(request):
    if not request.user.is_authenticated:
        return HttpResponse('Unauthorized', status=401)

    team = request.user.team_set.get()
    app_url = request.GET.get('appUrl') or (team.app_urls and team.app_urls[0])

    if not app_url:
        return HttpResponse(status=404)

    request.user.temporary_token = secrets.token_urlsafe(32)
    request.user.save()
    state = urllib.parse.quote(json.dumps({
        'action': 'mpeditor',
        'token': team.api_token,
        'temporaryToken': request.user.temporary_token,
        'actionId': request.GET.get('actionId'),
        'apiURL': request.build_absolute_uri('/')
    }))

    return redirect("{}#state={}".format(app_url, state))


@require_http_methods(['PATCH'])
def change_password(request):
    """Change the password of a regular User."""
    if not request.user.is_authenticated:
        return JsonResponse({}, status=401)

    try:
        body = json.loads(request.body)
    except (TypeError, json.decoder.JSONDecodeError):
        return JsonResponse({'error': 'Cannot parse request body'}, status=400)

    old_password = body.get('oldPassword')
    new_password = body.get('newPassword')

    if not old_password or not new_password:
        return JsonResponse({'error': 'Missing payload'}, status=400)

    if not request.user.check_password(old_password):
        return JsonResponse({'error': 'Incorrect old password'}, status=400)

    try:
        validate_password(new_password, user)
    except ValidationError as err:
        return JsonResponse({'error': err.messages[0]}, status=400)

    request.user.set_password(new_password)
    request.user.save()
    update_session_auth_hash(request, request.user)

    return JsonResponse({})
