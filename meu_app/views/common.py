from django.http import JsonResponse, HttpResponse


def health(request):
    return JsonResponse({"status": "ok", "service": "tcc-back", "version": "1.0"})


def index(request):
    return HttpResponse("API OK", content_type="text/plain")
